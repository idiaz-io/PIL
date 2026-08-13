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
