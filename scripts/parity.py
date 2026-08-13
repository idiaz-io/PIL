"""Prove the migration: PIL's translators against AXO's, over every captured payload.

    make parity AXO_PATH=../axo

Byte-identical or it fails (§5 Step 3), with one documented exception.

**What counts as a failure.** Differing output, obviously. But also: an empty corpus, and
any source whose corpus is thinner than ``--min-per-source``. Both used to pass. A harness
that returns success having compared nothing reports Definition of Done item 7 as satisfied
while holding no evidence, and that is worse than having no harness — it gets read as proof.
``--demo`` exists for exercising the machinery and never reports a parity result.

**What this proves, precisely.** Every field except ``tenant_id`` must match byte for
byte. ``tenant_id`` is excluded because PIL takes the tenant from the adapter instance's
configuration while AXO reads it from the vendor payload — the single intentional
difference, decided in ADR-0004 and printed on every run so that the weaker claim is
never mistaken for a full match. PIL's tenant is separately asserted to equal the
configured one.

**How it runs.** AXO's normalisers execute in a subprocess under AXO's own interpreter,
because they need pydantic, httpx, fastapi and sqlalchemy. PIL's virtualenv has none of
those and must not — I-3 means PIL never depends on a product, including its dependency
tree. This module therefore never imports AXO; it exchanges JSON with
``scripts/_axo_driver.py`` across a process boundary.

**Determinism.** Both sides run under the same frozen clock and with ``TZ=UTC``. AXO's
normalisers fall back to ``datetime.utcnow()`` when a payload carries no usable
timestamp, and parse epochs in local time. Without pinning both, "byte-identical" would
not be a claim anyone could make.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Pin the timezone for THIS process, before anything reads a clock.
#
# Both implementations parse epoch timestamps with local-time `datetime.fromtimestamp`
# (`normaliser.py:100`), so each side answers according to wherever it happens to be
# running. Setting TZ only for AXO's subprocess is not enough — it makes the harness
# report a difference that is an artefact of the harness rather than of the code under
# test. This was a real bug here, caught by the epoch fixture in --demo.
os.environ["TZ"] = "UTC"
time.tzset()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "packages" / "adapters" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "packages" / "contracts" / "src"))

from pil_adapters import TRANSLATOR_TYPES, AdapterConfig, FrozenClock, get_translator  # noqa: E402
from pil_contracts import canonical_text  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DRIVER = Path(__file__).resolve().parent / "_axo_driver.py"

#: Any instant would do, as long as both sides use the same one.
FROZEN_INSTANT = datetime(2026, 3, 14, 15, 9, 26, 535897, tzinfo=UTC)

#: The tenant the harness configures PIL with. Deliberately unlike anything a fixture
#: could contain, so that a translator leaking a payload-derived tenant is obvious.
HARNESS_TENANT = "parity-harness-tenant"

#: Excluded from the byte comparison. See ADR-0004.
EXCLUDED_FIELDS = ("tenant_id",)

#: Fixtures a source needs before its result means anything. The lower bound in
#: IDI-195 §D6 step 1, "capture 10-20 real payloads per source". Named rather than
#: inlined so that relaxing it is a visible edit.
DEFAULT_MIN_PER_SOURCE = 10

#: Captured sources that deliberately have no PIL translator, with the reason.
#:
#: These are reported and skipped rather than compared. Without this they would be
#: collected, fail to find a translator on both sides, and be scored as "both raised
#: (matching)" — a source with no implementation counted as evidence of parity.
OUT_OF_SCOPE_SOURCES: dict[str, str] = {
    "sl1_poller": (
        "sl_poller.py:238 _normalise_api_alert returns a database row shape, not a "
        "StandardAlert — ADR-0005 defers it, and mapping ext_ticket_ref and counter onto "
        "the envelope is an envelope question needing its own ADR. Captured as evidence "
        "for that future decision, not as a parity target."
    ),
}

#: Payloads used by --demo to prove the harness itself works before real fixtures exist.
DEMO_PAYLOADS: dict[str, list[dict[str, Any]]] = {
    "sciencelogic": [
        {
            "xid": "42",
            "yname": "db01",
            "severity": "4",
            "category": "service",
            "message": "SQL Server stopped",
            "organization_id": "99",
        },
        {"id": "7", "severity": "emergency", "description": "disk full", "epoch": 1770000000},
        {"alert_id": "", "event_id": "e-9", "device": {"name": "web01"}},
    ],
    "connectwise": [
        {
            "id": 12345,
            "summary": "SQL Server stopped on PROD-DB-01",
            "company": {"id": 100, "identifier": "AcmeCorp"},
            "priority": {"id": 1},
            "type": {"name": "Service"},
            "dateEntered": "2025-03-10T14:30:00Z",
        },
    ],
    "fleet": [
        {
            "host_uuid": "aaaabbbbccccdddd",
            "host_name": "mac-01",
            "policy_name": "FileVault enabled",
            "team_name": "Acme",
        },
        {"failing_policies": [{"host_uuid": "eeeeffff11112222", "policy_name": "Disk space"}]},
    ],
    "sl1": [{"event_id": "1", "severity": "2", "message": "IIS application pool stopped"}],
    "addigy": [
        {
            "id": "a1",
            "severity": "high",
            "alert_message": "FileVault disabled",
            "policy_id": "pol-1",
            "agentid": "agent-9",
        }
    ],
    "legacy": [{"id": "x", "platform": "custom", "severity": "P1", "message": "something"}],
}


@dataclass
class Case:
    source: str
    payload: dict[str, Any]
    origin: str


@dataclass
class Outcome:
    case: Case
    matched: bool
    detail: str = ""
    axo_tenant: str = ""
    pil_hint: str = ""


def collect_fixtures(fixtures_root: Path) -> tuple[list[Case], dict[str, int]]:
    """Every comparable fixture, plus a count of what was deliberately skipped.

    The skipped count is returned rather than swallowed so the run can print it. A harness
    that quietly drops part of its corpus reads as having covered everything.
    """
    cases: list[Case] = []
    skipped: dict[str, int] = {}
    if not fixtures_root.is_dir():
        return cases, skipped
    for source_dir in sorted(fixtures_root.iterdir()):
        if not source_dir.is_dir() or source_dir.name.startswith("_"):
            continue
        if source_dir.name in OUT_OF_SCOPE_SOURCES:
            skipped[source_dir.name] = len(list(source_dir.rglob("*.json")))
            continue
        for path in sorted(source_dir.rglob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except ValueError as exc:
                print(f"  ! skipping unreadable fixture {path}: {exc}")
                continue
            cases.append(
                Case(source_dir.name, payload, str(path.relative_to(fixtures_root.parent)))
            )
    return cases, skipped


def golden_path(golden_root: Path, case: Case) -> Path:
    """Where a case's expected output lives.

    Keyed on the fixture's path rather than on its content, so that renaming a fixture
    shows up as a deleted and an added golden file rather than as a silent orphan.
    """
    stem = Path(case.origin).with_suffix(".json").name
    return golden_root / case.source / stem


def record_golden(golden_root: Path, cases: list[Case], axo_results: list[dict[str, Any]]) -> int:
    """Write AXO's current output as the specification. Returns the number written.

    IDI-195 §D6 step 2: "Run each through AXO's **current** code and commit the output.
    That saved output is the specification — not the docs, not anyone's memory."

    Canonical JSON, so a re-record produces a byte-identical file when nothing changed and
    the diff is empty. A diff here is the signal: it means AXO's behaviour moved.
    """
    written = 0
    for case, result in zip(cases, axo_results, strict=True):
        path = golden_path(golden_root, case)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Underscore-prefixed keys are the harness's own annotations (the tenant report),
        # not AXO's output. Recording them would make the specification depend on the
        # harness's internals.
        body: dict[str, Any] = {"ok": result["ok"]}
        if result["ok"]:
            body["projection"] = {
                k: v for k, v in result["projection"].items() if not k.startswith("_")
            }
        else:
            # The error *type* is the specification, not the message — messages carry
            # paths and line numbers that move between machines.
            body["error_type"] = str(result.get("error", "")).split(":", 1)[0]
        path.write_text(canonical_text(body) + "\n", encoding="utf-8")
        written += 1
    return written


def compare_to_golden(golden_root: Path, case: Case, axo: dict[str, Any]) -> str | None:
    """Check AXO's live output against the committed specification.

    Returns a description of the difference, or None when they agree or no golden file
    exists yet.

    This is what makes the specification a *specification*. Without it the harness compares
    PIL against whatever AXO happens to do today, so an accidental change to AXO's
    normalisers silently redefines what "correct" means and parity still passes.
    """
    path = golden_path(golden_root, case)
    if not path.is_file():
        return None

    expected = json.loads(path.read_text(encoding="utf-8"))
    actual: dict[str, Any] = {"ok": axo["ok"]}
    if axo["ok"]:
        actual["projection"] = {k: v for k, v in axo["projection"].items() if not k.startswith("_")}
    else:
        actual["error_type"] = str(axo.get("error", "")).split(":", 1)[0]

    if canonical_text(expected) == canonical_text(actual):
        return None
    return (
        f"      AXO no longer matches the committed specification\n"
        f"        expected: {canonical_text(expected)}\n"
        f"        actual:   {canonical_text(actual)}\n"
        f"        ({_display(path)})"
    )


def _display(path: Path) -> str:
    """Repo-relative when possible, absolute otherwise.

    ``--golden`` can point anywhere, including a temporary directory outside the repo, so
    this cannot assume the path is under ``REPO_ROOT``.
    """
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def demo_cases() -> list[Case]:
    return [
        Case(source, payload, f"--demo[{source}][{index}]")
        for source, payloads in DEMO_PAYLOADS.items()
        for index, payload in enumerate(payloads)
    ]


def run_axo(axo_path: Path, cases: list[Case], python: Path) -> list[dict[str, Any]]:
    job = {
        "axo_path": str(axo_path),
        "frozen_iso": FROZEN_INSTANT.isoformat(),
        "cases": [{"source": c.source, "payload": c.payload} for c in cases],
    }
    env = {**os.environ, "TZ": "UTC", "PYTHONHASHSEED": "0"}
    proc = subprocess.run(
        [str(python), str(DRIVER)],
        input=json.dumps(job),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if proc.returncode != 0 and not proc.stdout.strip():
        raise SystemExit(
            f"AXO driver failed (exit {proc.returncode}).\nstderr:\n{proc.stderr[-4000:]}"
        )
    try:
        payload = json.loads(proc.stdout)
    except ValueError as exc:
        raise SystemExit(
            f"AXO driver produced no usable JSON: {exc}\n"
            f"stdout:\n{proc.stdout[-2000:]}\nstderr:\n{proc.stderr[-2000:]}"
        ) from exc
    if "fatal" in payload:
        raise SystemExit(f"AXO driver could not load AXO's normalisers: {payload['fatal']}")
    return payload["results"]


def run_pil(case: Case) -> dict[str, Any]:
    """Project PIL's envelope onto the same shape the AXO driver reports."""
    translator = get_translator(
        case.source, AdapterConfig(tenant_id=HARNESS_TENANT), FrozenClock(FROZEN_INSTANT)
    )
    envelope = translator.translate(case.payload)
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
        },
        "tenant_id": envelope.tenant_id,
        "tenant_hint": envelope.tenant_hint.tenant_id or "",
    }


def compare(case: Case, axo: dict[str, Any], pil: dict[str, Any]) -> Outcome:
    # An exception is a legitimate outcome. Both sides raising is a match; one raising
    # and the other not is exactly the kind of difference this harness exists to find.
    if not axo["ok"] or not pil["ok"]:
        if not axo["ok"] and not pil["ok"]:
            return Outcome(case, True, "both raised (matching)")
        which = "AXO" if not axo["ok"] else "PIL"
        error = axo.get("error") if not axo["ok"] else pil.get("error")
        return Outcome(case, False, f"only {which} raised: {error}")

    axo_projection = {k: v for k, v in axo["projection"].items() if not k.startswith("_")}
    pil_projection = pil["projection"]

    differences = []
    for field in sorted(set(axo_projection) | set(pil_projection)):
        if field in EXCLUDED_FIELDS:
            continue
        left = canonical_text(axo_projection.get(field))
        right = canonical_text(pil_projection.get(field))
        if left != right:
            differences.append(f"      {field}:\n        AXO: {left}\n        PIL: {right}")

    outcome = Outcome(
        case,
        not differences,
        "\n".join(differences),
        axo_tenant=axo["projection"].get("_axo_tenant_id", ""),
        pil_hint=pil["tenant_hint"],
    )

    if pil["tenant_id"] != HARNESS_TENANT:
        return Outcome(
            case,
            False,
            f"      I-5 VIOLATION: PIL emitted tenant {pil['tenant_id']!r}, "
            f"expected {HARNESS_TENANT!r}",
        )
    return outcome


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--axo-path", default="../axo", help="path to an AXO checkout")
    parser.add_argument("--fixtures", default=str(REPO_ROOT / "fixtures"))
    parser.add_argument(
        "--demo",
        action="store_true",
        help="run against built-in synthetic payloads to prove the harness works. "
        "This is NOT a parity proof — it exercises the machinery, not real traffic.",
    )
    parser.add_argument("--python", default="", help="AXO's interpreter (default: its .venv)")
    parser.add_argument(
        "--golden",
        default=str(REPO_ROOT / "fixtures" / "_expected"),
        help="directory of committed AXO output — the specification (IDI-195 §D6 step 2)",
    )
    parser.add_argument(
        "--record-golden",
        action="store_true",
        help="write AXO's current output to --golden and exit. This DEFINES the "
        "specification, so the diff it produces is the thing to review: any change to a "
        "committed file means AXO's behaviour moved.",
    )
    parser.add_argument(
        "--no-golden",
        action="store_true",
        help="compare only against AXO running live, skipping the committed specification. "
        "For local iteration; CI should not use it.",
    )
    parser.add_argument(
        "--min-per-source",
        type=int,
        default=DEFAULT_MIN_PER_SOURCE,
        help=f"fail if any source has fewer fixtures than this (default "
        f"{DEFAULT_MIN_PER_SOURCE}, the lower bound in IDI-195 §D6). Ignored with --demo.",
    )
    args = parser.parse_args()

    axo_path = Path(args.axo_path).resolve()
    if not (axo_path / "msp-platform").is_dir():
        raise SystemExit(f"no AXO checkout at {axo_path} (expected a msp-platform/ directory)")

    default_python = axo_path / "msp-platform" / ".venv" / "bin" / "python"
    python = Path(args.python) if args.python else default_python
    if not python.exists():
        raise SystemExit(
            f"AXO's interpreter not found at {python}.\n"
            "The harness runs AXO's normalisers under AXO's own Python because they need "
            "pydantic, httpx, fastapi and sqlalchemy, which PIL's venv deliberately lacks "
            "(I-3). Pass --python to point at one."
        )

    golden_root = Path(args.golden)

    skipped: dict[str, int] = {}
    if args.demo:
        cases = demo_cases()
    else:
        cases, skipped = collect_fixtures(Path(args.fixtures))

    print("PIL parity harness")
    print(f"  AXO checkout   {axo_path}")
    print(f"  interpreter    {python}")
    print(f"  frozen clock   {FROZEN_INSTANT.isoformat()}   TZ=UTC")
    excluded = ", ".join(EXCLUDED_FIELDS)
    print(f"  comparing      every field EXCEPT {excluded} (ADR-0004)")
    if args.demo or args.no_golden:
        print("  golden         not checked")
    else:
        print(f"  golden         {golden_root}")
    print(f"  cases          {len(cases)}")
    if args.demo:
        print("  MODE           --demo: synthetic payloads. Proves the harness, not parity.")
    # Printed, never silent. A harness that drops part of its corpus without saying so
    # reads as having covered everything.
    for source, count in sorted(skipped.items()):
        print(f"  SKIPPED        {source}: {count} fixture(s) — {OUT_OF_SCOPE_SOURCES[source]}")
    print()

    if not cases:
        print("FAILED — no fixtures, so nothing was compared.")
        print()
        print("An empty corpus is not a pass. This command exits non-zero here on purpose:")
        print("Definition of Done item 7 asks for parity proven for every source, and a")
        print("harness that returns success having compared nothing reports that item as")
        print("satisfied while holding no evidence at all. A check that cannot fail is worse")
        print("than no check, because it gets read as proof.")
        print()
        print("The corpus is captured from AXO in production by")
        print("backend/services/pil_capture.py, gated on PIL_CAPTURE_ENABLED and requiring")
        print("PIL_CAPTURE_SALT — see docs/adr/0007-fixture-capture-and-scrubbing.md.")
        print()
        print("To exercise the machinery without a corpus, use --demo. That is deliberately")
        print("a separate flag: it proves the harness runs, it does not prove parity.")
        return 1

    axo_results = run_axo(axo_path, cases, python)

    if args.record_golden:
        written = record_golden(golden_root, cases, axo_results)
        print(f"Recorded {written} expected output(s) to {golden_root}.")
        print()
        print("This DEFINES the specification (§D6 step 2). Review the diff before")
        print("committing: any change to a file that already existed means AXO's behaviour")
        print("moved, and that is a finding rather than a routine update.")
        return 0

    # AXO against its own committed output, before PIL is considered at all. A drift here
    # invalidates the comparison that follows, because it means the thing PIL is being
    # measured against is no longer the thing that was agreed.
    drifted: list[tuple[Case, str]] = []
    if not args.no_golden and not args.demo:
        for case, axo_result in zip(cases, axo_results, strict=True):
            difference = compare_to_golden(golden_root, case, axo_result)
            if difference is not None:
                drifted.append((case, difference))

    outcomes: list[Outcome] = []
    for case, axo_result in zip(cases, axo_results, strict=True):
        try:
            pil_result = run_pil(case)
        except Exception as exc:
            pil_result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        outcomes.append(compare(case, axo_result, pil_result))

    failures = [o for o in outcomes if not o.matched]
    by_source: dict[str, list[Outcome]] = {}
    for outcome in outcomes:
        by_source.setdefault(outcome.case.source, []).append(outcome)

    for source in sorted(by_source):
        results = by_source[source]
        bad = [o for o in results if not o.matched]
        mark = "FAIL" if bad else "ok"
        print(f"  [{mark:>4}] {source:<14} {len(results) - len(bad)}/{len(results)} identical")
        for outcome in bad:
            print(f"         {outcome.case.origin}")
            print(outcome.detail)

    # The tenant report: what AXO would have attributed these messages to. This is the
    # number ADR-0004 exists to produce, and shadow mode extends it to live traffic.
    divergent = [o for o in outcomes if o.matched and o.axo_tenant and o.axo_tenant != o.pil_hint]
    unknown = [o for o in outcomes if o.axo_tenant == "unknown"]
    print()
    print("  Tenant report (excluded from the comparison, ADR-0004)")
    print(f'    payloads where AXO derived the literal "unknown": {len(unknown)}/{len(outcomes)}')
    if divergent:
        print(f"    payloads where AXO's tenant and PIL's hint disagree: {len(divergent)}")

    # Coverage. Definition of Done item 7 is "passes for every source AXO supports", and
    # a source with no fixtures is silently not checked — the per-source lines above only
    # report on directories that exist. Without this, deleting a fixture directory makes
    # the run greener, which is the wrong incentive.
    thin: list[str] = []
    if not args.demo:
        for source in sorted(TRANSLATOR_TYPES):
            count = len(by_source.get(source, ()))
            if count < args.min_per_source:
                thin.append(f"      {source:<14} {count} fixture(s), need {args.min_per_source}")

    print()
    if drifted:
        print(f"FAILED — AXO differs from its committed specification on {len(drifted)} case(s).")
        print()
        for case, difference in drifted:
            print(f"         {case.origin}")
            print(difference)
        print()
        print("The saved output IS the specification (§D6 step 2), so this is not a PIL")
        print("problem and PIL's result below is not meaningful until it is resolved.")
        print("Either AXO changed behaviour — a finding, and a ticket — or the change was")
        print("deliberate, in which case re-record with --record-golden and review that diff.")
        return 1

    if failures:
        print(f"FAILED — {len(failures)} of {len(outcomes)} payloads differ.")
        print("Each difference is either a porting bug or a known difference that belongs in")
        print("docs/known-differences.md with a ticket. It is not something to fix in the")
        print("translator while migrating (I-10).")
        return 1

    if thin:
        print(f"FAILED — {len(outcomes)} payloads matched, but coverage is short.")
        print()
        print("  Sources below the minimum:")
        print("\n".join(thin))
        print()
        print("Every source AXO supports needs a corpus of its own (DoD 7). Matching on the")
        print("sources that happen to have fixtures is not parity for the sources that do")
        print("not. Lower the bar with --min-per-source only when you mean to.")
        return 1

    if args.demo:
        print(f"Harness OK — {len(outcomes)} synthetic payloads agree.")
        print()
        print("This is NOT a parity result and must not be recorded as one. It proves the")
        print("machinery runs against payloads written by hand. Real parity needs the")
        print("captured corpus; run without --demo.")
        return 0

    print(f"PASSED — {len(outcomes)} payloads, byte-identical except {excluded}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
