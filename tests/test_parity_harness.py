"""The parity harness, tested against the ways it used to lie.

The harness is the thing that decides whether the migration is safe, so its failure modes
matter as much as the translators'. Both cases below returned success before IDI-195:

* an empty corpus — nothing compared, exit 0
* a source with no fixtures — silently absent from the per-source report

Neither is a parity result, and both were reported through the same green check mark that a
real pass uses. These tests exist so that cannot come back quietly.

The harness itself needs an AXO checkout and AXO's interpreter, so these tests do not run
it end to end. They drive ``main`` with a fixtures directory under the test's control and
assert on the exit code, which is the part CI reads.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

parity = pytest.importorskip("parity", reason="parity harness not importable")

#: A checkout of AXO is needed before the harness gets as far as comparing anything.
AXO = Path("../axo").resolve()
NEEDS_AXO = pytest.mark.skipif(
    not (AXO / "msp-platform").is_dir(),
    reason="no AXO checkout beside PIL; the harness cannot run without one",
)


def run(argv: list[str]) -> int:
    """Invoke the harness's entry point, returning its exit code."""
    original = sys.argv
    sys.argv = ["parity.py", *argv]
    try:
        return parity.main()
    except SystemExit as exc:  # argparse, or a missing checkout
        return int(exc.code or 0)
    finally:
        sys.argv = original


@NEEDS_AXO
def test_an_empty_corpus_fails(tmp_path):
    """The headline false pass: success having compared nothing.

    Definition of Done item 7 is read off this exit code. If it can be 0 with no
    fixtures, the item reports satisfied while holding no evidence.
    """
    empty = tmp_path / "fixtures"
    empty.mkdir()
    assert run(["--axo-path", str(AXO), "--fixtures", str(empty)]) == 1


@NEEDS_AXO
def test_a_missing_fixtures_directory_fails(tmp_path):
    """Deleting the corpus must not be a way to make the run pass."""
    assert run(["--axo-path", str(AXO), "--fixtures", str(tmp_path / "nope")]) == 1


@NEEDS_AXO
def test_a_source_with_a_thin_corpus_fails(tmp_path):
    """Coverage is per source, not in aggregate.

    One source with a full corpus must not carry five sources with none. The payload
    used here is one the ScienceLogic normaliser handles, so the comparison itself
    passes and the *only* reason for a non-zero exit is short coverage.
    """
    fixtures = tmp_path / "fixtures"
    (fixtures / "sciencelogic").mkdir(parents=True)
    for index in range(3):
        (fixtures / "sciencelogic" / f"{index}.json").write_text(
            json.dumps({"id": str(index), "severity": "4", "message": "disk full"}),
            encoding="utf-8",
        )

    argv = ["--axo-path", str(AXO), "--fixtures", str(fixtures)]
    assert run([*argv, "--min-per-source", "10"]) == 1, (
        "three fixtures for one source, none for the other five, must not pass"
    )

    # And the bar is a deliberate act, not an accident: lowered far enough, the same
    # corpus passes. This asserts the failure above was coverage and not a difference.
    assert run([*argv, "--min-per-source", "0"]) == 0


def test_demo_mode_is_not_reported_as_parity():
    """--demo must never be recordable as evidence.

    It runs synthetic payloads written by hand. The distinction is the whole reason the
    flag exists, so the wording that carries it is worth pinning: if someone reuses the
    real summary line here, a demo run becomes quotable as a pass.
    """
    source = Path(parity.__file__).read_text(encoding="utf-8")
    assert "Harness OK" in source, "demo mode must not print the real PASSED summary"
    assert "NOT a parity result" in source


def test_the_minimum_per_source_default_matches_the_ticket():
    """IDI-195 §D6 step 1: "Capture 10-20 real payloads per source".

    Pinned so that lowering the bar for everyone is a visible edit to a named constant
    rather than a quiet change to a default nobody reads.
    """
    assert parity.DEFAULT_MIN_PER_SOURCE == 10


def test_every_known_source_is_subject_to_the_coverage_floor():
    """The floor is driven by PIL's registry, not by a hand-maintained list.

    If it were a list, adding a translator would leave it uncovered — the source would
    have no fixtures and nothing would say so.
    """
    from pil_adapters import TRANSLATOR_TYPES

    assert parity.TRANSLATOR_TYPES is TRANSLATOR_TYPES
    assert set(TRANSLATOR_TYPES) >= {
        "sciencelogic",
        "sl1",
        "connectwise",
        "fleet",
        "addigy",
        "legacy",
    }


def test_demo_cases_reads_the_synthetic_corpus():
    """--demo replays fixtures/_synthetic/, not a hardcoded dict (mechanism 2).

    No AXO checkout needed -- this only proves the wiring collects the right files, not
    that AXO agrees with them. That proof needs a live checkout; see make parity-demo.
    """
    cases = parity.demo_cases()

    sources = {c.source for c in cases}
    assert sources == {"sciencelogic", "sl1", "connectwise", "fleet", "addigy", "legacy"}, (
        "a source directory went missing, or one was added to fixtures/_synthetic/ "
        "without a matching translator"
    )
    assert len(cases) == 33, (
        "fixtures/_synthetic/'s fixture count changed -- update this if the change was "
        "deliberate, or find out why it wasn't"
    )
    # Reuses collect_fixtures()'s own origin format -- a real path, not a synthetic label,
    # so a failure in --demo points at the exact file to open.
    assert all(c.origin.startswith("_synthetic/") for c in cases)


@NEEDS_AXO
def test_an_out_of_scope_source_is_skipped_and_reported(tmp_path, capsys):
    """A source with no PIL translator must not be scored as a match.

    Collected and compared, `sl1_poller` fails to find a translator on *both* sides, which
    the comparison would score as "both raised (matching)" — a source with no
    implementation counted as evidence of parity. It is skipped instead, and the skip is
    printed, because a harness that silently drops part of its corpus reads as having
    covered everything.
    """
    fixtures = tmp_path / "fixtures"
    (fixtures / "sl1_poller").mkdir(parents=True)
    (fixtures / "sl1_poller" / "a.json").write_text('{"id": "1"}', encoding="utf-8")

    # Nothing comparable remains, so this exits 1 on the empty-corpus rule — the point
    # being that the sl1_poller fixture did not quietly become a passing case.
    assert run(["--axo-path", str(AXO), "--fixtures", str(fixtures)]) == 1

    out = capsys.readouterr().out
    assert "SKIPPED" in out
    assert "sl1_poller" in out
    assert "ADR-0005" in out, "the skip should say why, not just that"


def test_out_of_scope_sources_are_documented_with_a_reason():
    """A bare list would let someone silence a source without justifying it."""
    assert parity.OUT_OF_SCOPE_SOURCES
    for source, reason in parity.OUT_OF_SCOPE_SOURCES.items():
        assert len(reason) > 80, f"{source} needs a real reason, not a label"


def test_no_out_of_scope_source_has_a_translator():
    """If a translator appears for one, it stops being out of scope and the entry is stale."""
    from pil_adapters import TRANSLATOR_TYPES

    overlap = set(parity.OUT_OF_SCOPE_SOURCES) & set(TRANSLATOR_TYPES)
    assert not overlap, f"{overlap} have translators and should be compared, not skipped"


# ----------------------------------------------------------------------------------
# The committed specification  (IDI-195 §D6 step 2)
# ----------------------------------------------------------------------------------
#
# "Run each through AXO's current code and commit the output. That saved output is the
# specification — not the docs, not anyone's memory."
#
# Without this, the harness compares PIL against whatever AXO happens to do today: an
# accidental change to AXO's normalisers silently redefines "correct" and parity still
# passes. These tests are the ones that make the specification a specification.


def _corpus(tmp_path, count=3):
    """A small ScienceLogic corpus the real AXO normaliser handles."""
    fixtures = tmp_path / "fixtures"
    (fixtures / "sciencelogic").mkdir(parents=True)
    for index in range(count):
        (fixtures / "sciencelogic" / f"{index}.json").write_text(
            json.dumps({"id": str(index), "severity": "4", "message": "disk full"}),
            encoding="utf-8",
        )
    return fixtures


@NEEDS_AXO
def test_recording_golden_then_comparing_passes(tmp_path):
    """The happy path: record AXO's output, then a run agrees with it."""
    fixtures = _corpus(tmp_path)
    golden = tmp_path / "_expected"
    argv = [
        "--axo-path",
        str(AXO),
        "--fixtures",
        str(fixtures),
        "--golden",
        str(golden),
        "--min-per-source",
        "0",
    ]

    assert run([*argv, "--record-golden"]) == 0
    assert list(golden.rglob("*.json")), "recording must actually write files"
    assert run(argv) == 0


@NEEDS_AXO
def test_axo_drifting_from_the_specification_fails(tmp_path, capsys):
    """The test this whole mechanism exists for.

    A golden file that no longer matches AXO's live output means AXO's behaviour moved.
    That has to fail loudly, and it has to be distinguishable from a PIL porting bug —
    PIL's result is not meaningful once the specification has shifted underneath it.
    """
    fixtures = _corpus(tmp_path)
    golden = tmp_path / "_expected"
    argv = [
        "--axo-path",
        str(AXO),
        "--fixtures",
        str(fixtures),
        "--golden",
        str(golden),
        "--min-per-source",
        "0",
    ]
    assert run([*argv, "--record-golden"]) == 0

    # Stand in for AXO's behaviour changing: edit the committed specification.
    victim = next(iter(golden.rglob("*.json")))
    recorded = json.loads(victim.read_text(encoding="utf-8"))
    recorded["projection"]["severity"] = "P9-something-nobody-emits"
    victim.write_text(json.dumps(recorded), encoding="utf-8")

    assert run(argv) == 1

    out = capsys.readouterr().out
    assert "committed specification" in out
    assert "not a PIL" in out, "must not read as a porting bug"
    assert "--record-golden" in out, "should say how to accept a deliberate change"


@NEEDS_AXO
def test_no_golden_skips_the_specification_check(tmp_path):
    """For local iteration. CI does not use it, and the header says when it is off."""
    fixtures = _corpus(tmp_path)
    golden = tmp_path / "_expected"
    argv = [
        "--axo-path",
        str(AXO),
        "--fixtures",
        str(fixtures),
        "--golden",
        str(golden),
        "--min-per-source",
        "0",
    ]
    assert run([*argv, "--record-golden"]) == 0

    victim = next(iter(golden.rglob("*.json")))
    victim.write_text('{"ok": true, "projection": {"severity": "wrong"}}', encoding="utf-8")

    assert run([*argv, "--no-golden"]) == 0, "--no-golden must skip the drift check"
    assert run(argv) == 1, "and without it, the drift is caught"


@NEEDS_AXO
def test_a_missing_golden_file_does_not_fail_the_run(tmp_path):
    """Before the corpus is recorded there is nothing to compare against.

    Deliberately not an error: the coverage floor already fails a run with no corpus, and
    making a missing golden file fatal too would mean a newly captured fixture breaks CI
    before anyone has had the chance to record it.
    """
    fixtures = _corpus(tmp_path)
    argv = [
        "--axo-path",
        str(AXO),
        "--fixtures",
        str(fixtures),
        "--golden",
        str(tmp_path / "absent"),
        "--min-per-source",
        "0",
    ]
    assert run(argv) == 0


@NEEDS_AXO
def test_recording_is_byte_stable(tmp_path):
    """A re-record with no behaviour change must produce an empty diff.

    Canonical JSON, so reviewing "did AXO change" is reading a diff rather than trusting
    that key order happened to be preserved.
    """
    fixtures = _corpus(tmp_path)
    golden = tmp_path / "_expected"
    argv = [
        "--axo-path",
        str(AXO),
        "--fixtures",
        str(fixtures),
        "--golden",
        str(golden),
        "--min-per-source",
        "0",
        "--record-golden",
    ]
    assert run(argv) == 0
    first = {p.name: p.read_bytes() for p in sorted(golden.rglob("*.json"))}

    assert run(argv) == 0
    second = {p.name: p.read_bytes() for p in sorted(golden.rglob("*.json"))}

    assert first == second


@NEEDS_AXO
def test_the_specification_excludes_harness_annotations(tmp_path):
    """Underscore-prefixed keys are the harness's tenant report, not AXO's output.

    Recording them would make the specification depend on the harness's internals, so a
    change to the tenant report would read as a change in AXO's behaviour.
    """
    fixtures = _corpus(tmp_path, count=1)
    golden = tmp_path / "_expected"
    assert (
        run(
            [
                "--axo-path",
                str(AXO),
                "--fixtures",
                str(fixtures),
                "--golden",
                str(golden),
                "--min-per-source",
                "0",
                "--record-golden",
            ]
        )
        == 0
    )

    recorded = json.loads(next(iter(golden.rglob("*.json"))).read_text(encoding="utf-8"))
    assert not [k for k in recorded.get("projection", {}) if k.startswith("_")]
