"""The invariants, enforced by test rather than by intention.

`CLAUDE.md`: "The invariants above are enforced by a test or a lint rule, not by
intention." Definition of Done items 5, 6 and 7 name three of these specifically.

Lint covers the static case; these tests cover what lint cannot see — dynamic imports,
transitive dependencies, and behaviour over every fixture in the corpus.
"""

from __future__ import annotations

import ast
import json
import tomllib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pil_adapters import AdapterConfig, FrozenClock, build_registry
from pil_adapters.base import Translation

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_SRC = REPO_ROOT / "packages" / "contracts" / "src"
ADAPTERS_SRC = REPO_ROOT / "packages" / "adapters" / "src"
GRAPH_SRC = REPO_ROOT / "packages" / "graph" / "src"
CAPABILITIES_SRC = REPO_ROOT / "packages" / "capabilities" / "src"
FIXTURES = REPO_ROOT / "fixtures"

#: Every MERP product. Nothing in PIL may import any of them, nor AXO's `backend`
#: package. Kept in step with the banned-api list in pyproject.toml.
PRODUCT_MODULES = frozenset(
    {"axo", "quill", "vigil", "otto", "guardrails", "pavo", "remi", "backend"}
)

CLOCK = FrozenClock(datetime(2026, 3, 14, 15, 9, 26, 535897, tzinfo=UTC))


def python_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.py"))


def imported_roots(path: Path) -> set[str]:
    """Top-level module names imported by a file, including inside functions."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


# ----------------------------------------------------------------------------------
# I-3 · PIL never depends on a product  (Definition of Done item 6)
# ----------------------------------------------------------------------------------


def test_no_pil_module_imports_a_product():
    """Catches dynamic and function-local imports that the ruff rule cannot see."""
    offenders: list[str] = []
    for source_root in (CONTRACTS_SRC, ADAPTERS_SRC, GRAPH_SRC, CAPABILITIES_SRC):
        for path in python_files(source_root):
            banned = imported_roots(path) & PRODUCT_MODULES
            if banned:
                offenders.append(f"{path.relative_to(REPO_ROOT)} imports {sorted(banned)}")
    assert not offenders, (
        "I-3: the dependency arrow points one way. If PIL needs this, it belonged in "
        "PIL.\n" + "\n".join(offenders)
    )


def test_the_lint_rule_and_this_test_ban_the_same_names():
    """Two mechanisms are only worth having if they cannot drift apart."""
    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    banned = config["tool"]["ruff"]["lint"]["flake8-tidy-imports"]["banned-api"]
    assert set(banned) == PRODUCT_MODULES


# ----------------------------------------------------------------------------------
# contracts has zero dependencies  (Definition of Done item 5)
# ----------------------------------------------------------------------------------


def test_contracts_declares_no_dependencies():
    config = tomllib.loads(
        (REPO_ROOT / "packages" / "contracts" / "pyproject.toml").read_text(encoding="utf-8")
    )
    assert config["project"]["dependencies"] == [], (
        "pil-contracts must stay dependency-free. QUILL takes it without adapters, and "
        "I-9 means a third-party serialiser's next release could change our bytes. "
        "Adding one is an ADR (ADR-0006)."
    )


def test_contracts_imports_nothing_from_this_repo_or_outside_the_stdlib():
    allowed = {"pil_contracts", "__future__"}
    stdlib = {
        "abc",
        "collections",
        "dataclasses",
        "datetime",
        "enum",
        "hashlib",
        "hmac",
        "json",
        "math",
        "re",
        "typing",
    }
    offenders: list[str] = []
    for path in python_files(CONTRACTS_SRC):
        for module in imported_roots(path) - allowed - stdlib:
            offenders.append(f"{path.relative_to(REPO_ROOT)} imports {module!r}")
    assert not offenders, "\n".join(offenders)


def test_adapters_depends_only_on_contracts_and_capabilities():
    config = tomllib.loads(
        (REPO_ROOT / "packages" / "adapters" / "pyproject.toml").read_text(encoding="utf-8")
    )
    names = [dep.split(">=")[0].split("==")[0].strip() for dep in config["project"]["dependencies"]]
    assert names == ["pil-contracts", "pil-capabilities"]


# ----------------------------------------------------------------------------------
# capabilities has zero dependencies, same posture as contracts (ADR-0012)
# ----------------------------------------------------------------------------------


def test_capabilities_declares_no_dependencies():
    config = tomllib.loads(
        (REPO_ROOT / "packages" / "capabilities" / "pyproject.toml").read_text(encoding="utf-8")
    )
    assert config["project"]["dependencies"] == [], (
        "pil-capabilities must stay dependency-free — same reasoning as pil-contracts "
        "(ADR-0006), applied here per ADR-0012: nothing about a closed permission "
        "vocabulary needs anything beyond the standard library."
    )


def test_capabilities_imports_nothing_from_this_repo_or_outside_the_stdlib():
    allowed = {"pil_capabilities", "__future__"}
    stdlib = {"collections", "dataclasses", "enum", "typing"}
    offenders: list[str] = []
    for path in python_files(CAPABILITIES_SRC):
        for module in imported_roots(path) - allowed - stdlib:
            offenders.append(f"{path.relative_to(REPO_ROOT)} imports {module!r}")
    assert not offenders, "\n".join(offenders)


# ----------------------------------------------------------------------------------
# I-1 · PIL is a library
# ----------------------------------------------------------------------------------


def test_nothing_in_pil_imports_a_web_framework_or_a_socket():
    """No HTTP surface, no server, no long-running process."""
    forbidden = {"fastapi", "flask", "django", "starlette", "uvicorn", "socket", "socketserver"}
    offenders: list[str] = []
    for source_root in (CONTRACTS_SRC, ADAPTERS_SRC, GRAPH_SRC, CAPABILITIES_SRC):
        for path in python_files(source_root):
            found = imported_roots(path) & forbidden
            if found:
                offenders.append(f"{path.relative_to(REPO_ROOT)} imports {sorted(found)}")
    assert not offenders, "I-1: PIL is a library, not a service.\n" + "\n".join(offenders)


# ----------------------------------------------------------------------------------
# I-5 · Tenant identity is never taken from input  (Definition of Done item 7)
# ----------------------------------------------------------------------------------


def test_translation_has_no_tenant_field():
    """The structural half of the enforcement.

    A translator returns a Translation, which has nowhere to put a tenant, so the base
    class is the only thing that can set one. This test guards that design against
    someone helpfully adding the field back.
    """
    fields = set(Translation.__dataclass_fields__)
    assert not {f for f in fields if "tenant" in f and f != "tenant_hint"}, (
        "I-5: Translation must not carry a tenant. Its absence is what makes it "
        "impossible for a translator to emit the wrong one."
    )


#: Payloads that try every route AXO uses to smuggle a tenant out of vendor input.
ADVERSARIAL_PAYLOADS = [
    {"client_id": "attacker", "client_name": "Attacker Ltd"},
    {"org_id": "attacker", "org_name": "Attacker Ltd"},
    {"organization_id": "attacker", "organization": "/api/organization/attacker"},
    {"company": {"id": "attacker", "identifier": "Attacker"}},
    {"team_name": "attacker", "policy_id": "attacker"},
    {"tenant_id": "attacker"},
    {"host_uuid": "aaaabbbbcccc", "policy_name": "x", "team": "attacker"},
]


@pytest.mark.parametrize("payload", ADVERSARIAL_PAYLOADS)
def test_no_translator_can_be_talked_into_another_tenant(payload):
    config = AdapterConfig(tenant_id="tenant-acme")
    for source, translator in build_registry(config, CLOCK).items():
        envelope = translator.translate(payload)
        assert envelope.tenant_id == "tenant-acme", (
            f"I-5 violated by {source}: a vendor payload changed the tenant."
        )


def test_a_blank_tenant_is_rejected_at_configuration_time():
    for blank in ("", "   "):
        with pytest.raises(ValueError, match="I-5"):
            AdapterConfig(tenant_id=blank)


@pytest.mark.skipif(not FIXTURES.exists(), reason="no fixtures captured yet")
def test_every_fixture_yields_the_configured_tenant():
    """The same guarantee, over real captured payloads rather than synthetic ones."""
    config = AdapterConfig(tenant_id="tenant-acme")
    registry = build_registry(config, CLOCK)

    checked = 0
    for source_dir in FIXTURES.iterdir():
        translator = registry.get(source_dir.name) if source_dir.is_dir() else None
        if translator is None:
            continue
        for path in source_dir.rglob("*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            try:
                envelope = translator.translate(payload)
            except Exception:
                # Payloads AXO itself cannot process live under _malformed/. A
                # translator raising on one is faithful behaviour, not a failure.
                continue
            assert envelope.tenant_id == "tenant-acme", f"I-5 violated by {path}"
            checked += 1

    if checked == 0:
        pytest.skip("fixtures directory exists but holds no payloads for known sources")


# ----------------------------------------------------------------------------------
# I-9 · Deterministic serialisation
# ----------------------------------------------------------------------------------


def test_translation_is_reproducible_under_a_frozen_clock():
    config = AdapterConfig(tenant_id="tenant-acme")
    payload = {"id": "1", "message": "disk full", "severity": "4"}

    for source, translator in build_registry(config, CLOCK).items():
        first = translator.translate(payload).to_canonical_json()
        for _ in range(5):
            assert translator.translate(payload).to_canonical_json() == first, (
                f"{source} is not deterministic under a frozen clock"
            )
