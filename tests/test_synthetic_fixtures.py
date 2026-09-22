"""Synthetic fixtures — hand-derived proof the six translators do what their source
says, for now, since every vendor source is unreachable (the homelab is offline) and
real capture per `docs/adr/0007-fixture-capture-and-scrubbing.md` cannot happen yet.

Not the parity corpus. ADR-0007 rejected hand-authored payloads as parity evidence —
"it can only contain the edge cases someone thought of." That rejection is about using
them as IDI-195 DoD 7 evidence; it says nothing against a different, narrower claim:
does PIL's own translator produce what its source and cited AXO line numbers say it
should. See `fixtures/_synthetic/README.md` for the full explanation.

**The rule that matters most**: each `fixtures/_synthetic/_expected/<source>/*.json` is
derived by hand from the translator's source, before ever running PIL — never recorded
from PIL's own output. Recording would make this a stability test, not a correctness
test. When a fixture fails here, the fix is either the fixture's derivation (it misread
the source) or the translator (a real bug) — never quietly editing the expected file to
match whatever PIL currently does.

Structurally invisible to the real parity corpus: `_synthetic/` starts with an
underscore, so `scripts/parity.py`'s own `collect_fixtures` already skips it (the same
mechanism that already excludes `_expected/`) — it can never be silently counted toward
DoD 7's coverage floor.
"""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pil_adapters import AdapterConfig, FrozenClock, get_translator
from pil_contracts import canonical_text

# One fixture (sciencelogic's epoch case) exercises AXO's documented local-time epoch
# defect (docs/known-differences.md, preserved defect 5) — datetime.fromtimestamp reads
# the process's local timezone. Pinning here is the same fix scripts/parity.py applies
# to itself, for the same reason: without it, this fixture's expected value would depend
# on whichever machine happened to run the test rather than being a portable fact about
# the code.
os.environ["TZ"] = "UTC"
time.tzset()

REPO_ROOT = Path(__file__).resolve().parent.parent
SYNTHETIC_ROOT = REPO_ROOT / "fixtures" / "_synthetic"
EXPECTED_ROOT = SYNTHETIC_ROOT / "_expected"

#: The same frozen instant test_translators.py, test_invariants.py and scripts/parity.py
#: each pin independently — not imported across modules, by this repo's own existing
#: convention (every translator-facing test site carries its own copy of the literal).
FROZEN_INSTANT = datetime(2026, 3, 14, 15, 9, 26, 535897, tzinfo=UTC)

#: Deliberately unlike anything a fixture payload could contain — mirrors
#: scripts/parity.py's HARNESS_TENANT, so a translator leaking a payload-derived tenant
#: would be obvious here too.
SYNTHETIC_TENANT = "synthetic-fixture-tenant"


def _cases() -> list[tuple[str, Path]]:
    cases: list[tuple[str, Path]] = []
    if not SYNTHETIC_ROOT.is_dir():
        return cases
    for source_dir in sorted(SYNTHETIC_ROOT.iterdir()):
        if not source_dir.is_dir() or source_dir.name.startswith("_"):
            continue
        cases.extend((source_dir.name, path) for path in sorted(source_dir.glob("*.json")))
    return cases


def _expected_path(source: str, input_path: Path) -> Path:
    return EXPECTED_ROOT / source / input_path.name


def _actual(source: str, payload: dict) -> dict:
    """Project PIL's translation onto the same {ok, projection|error_type} shape the
    expected files use — mirrors scripts/parity.py's own run_pil(), extended with
    tenant_hint, which matters here (several fixtures exist specifically to prove a
    documented tenant-hint defect reproduces)."""
    translator = get_translator(
        source, AdapterConfig(tenant_id=SYNTHETIC_TENANT), FrozenClock(FROZEN_INSTANT)
    )
    try:
        envelope = translator.translate(payload)
    except Exception as exc:  # a fixture may assert exactly this raises
        return {"ok": False, "error_type": type(exc).__name__}

    rendered = envelope.to_dict()
    return {
        "ok": True,
        "projection": {
            "alert_id": envelope.body.alert_id,
            "device_id": envelope.body.device_id,
            "device_name": envelope.body.device_name,
            "severity": envelope.body.severity,
            "category": envelope.body.category,
            "message": envelope.body.message,
            "occurred_at": rendered["occurred_at"],
            "device_history": rendered["body"]["device_history"],
            "raw_payload": rendered["raw_payload"],
            "tenant_hint": rendered["tenant_hint"],
        },
    }


CASES = _cases()


@pytest.mark.parametrize(("source", "input_path"), CASES, ids=[f"{s}/{p.name}" for s, p in CASES])
def test_synthetic_fixture_matches_hand_derived_expectation(source, input_path):
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    expected_path = _expected_path(source, input_path)
    assert expected_path.is_file(), (
        f"no expected file for {input_path.relative_to(REPO_ROOT)} — every synthetic "
        "input needs a hand-derived counterpart"
    )
    expected = json.loads(expected_path.read_text(encoding="utf-8"))

    actual = _actual(source, payload)

    assert canonical_text(actual) == canonical_text(expected), (
        f"{input_path.relative_to(REPO_ROOT)} disagrees with its hand-derived "
        "expectation. Per fixtures/_synthetic/README.md: do not edit the expected file "
        "to match — re-derive it by hand from the translator's source, or report this "
        "as a translator bug."
    )


def test_every_synthetic_source_has_a_registered_translator():
    """A source directory with no translator is a typo in the directory name, not a
    translator gap — unlike the real corpus, there is no OUT_OF_SCOPE_SOURCES concept
    for a corpus nobody captured from a system that doesn't exist yet."""
    from pil_adapters import TRANSLATOR_TYPES

    sources = {source for source, _ in CASES}
    unknown = sources - set(TRANSLATOR_TYPES)
    assert not unknown, f"no translator registered for: {sorted(unknown)}"
