# Known issues

Bugs found while verifying the repo, not fixed on the spot — recorded here so the fix is a
deliberate, reviewed change rather than something bundled into whatever else was being worked
on. Same discipline as `docs/known-differences.md`: report, don't quietly patch.

---

## `test_parity_harness.py` crashes instead of skipping, with a partial `~/axo` checkout

**Found:** 2026-09-14, verifying this repo by actually running `uv run pytest` rather than
trusting a previously reported pass/fail count (`docs/reference/pil-inventory.md` reports
121 passed / 11 skipped / 0 failed at commit `5530434`; the same commit, run here, produced
254 passed / **10 failed** / 1 skipped).

**Reproduction**

1. Have a sibling checkout at `../axo` (relative to the repo root) whose `msp-platform/`
   directory exists, but whose `msp-platform/.venv/` has never been built. This is a normal
   in-progress state — clone `axo`, don't run its setup yet.
2. Run `uv run pytest` from `~/pil`.
3. Ten tests in `tests/test_parity_harness.py` fail with an unhandled `ValueError`, not a
   skip.

**Why.** `tests/test_parity_harness.py:29-32` guards every test needing AXO with:

```python
AXO = Path("../axo").resolve()
NEEDS_AXO = pytest.mark.skipif(
    not (AXO / "msp-platform").is_dir(),
    reason="no AXO checkout beside PIL; the harness cannot run without one",
)
```

This only checks that the **directory** exists. It says nothing about whether AXO's
interpreter is built, which `scripts/parity.py:413-421` requires:

```python
default_python = axo_path / "msp-platform" / ".venv" / "bin" / "python"
...
if not python.exists():
    raise SystemExit(f"AXO's interpreter not found at {python}.\n...")
```

`SystemExit` with a **string** argument sets `.code` to that string, not an int. The test
harness's own `run()` helper assumes otherwise:

```python
def run(argv: list[str]) -> int:
    ...
    except SystemExit as exc:  # argparse, or a missing checkout
        return int(exc.code or 0)
```

`int("AXO's interpreter not found at ...")` raises `ValueError`, uncaught, failing the test
outright instead of skipping it or asserting a clean non-zero exit.

**Why this doesn't show up in CI.** A fresh CI checkout has no sibling `../axo` at all, so
`NEEDS_AXO`'s skip guard is true and these tests skip cleanly — the bug is latent everywhere
except a developer machine with a half-set-up AXO checkout next to PIL, which is an entirely
normal thing to have.

**The fix — either is a two-line change, not attempted here:**

- Tighten `NEEDS_AXO` to also check for the interpreter:
  `not (AXO / "msp-platform" / ".venv" / "bin" / "python").exists()` (or equivalent), so an
  incomplete checkout skips exactly like a missing one.
- Or make `run()` defensive: `return exc.code if isinstance(exc.code, int) else 1`, so any
  string exit reason (there may be more than the one shown above) fails the test cleanly
  instead of crashing it.

Either is correct; the first is cheaper and matches what the skip's own reason string already
claims ("the harness cannot run without one" — a checkout without a working interpreter is
exactly that).

**Not fixed here.** It's real, it's cheap, and it isn't the current phase's work — recording
it rather than bundling an unrelated fix into whatever commit comes next.

---

## `MERP-Agent-Handover.md` §6.2 gives edge-type *names*, not literal strings — filed against `idiaz-io/merp-console`

**Found:** 2026-09-15, cross-checking `pil_graph.vocabulary`'s 13 edge types byte-for-byte
against AXO's `packages/itkg/vocab.go` and against the handover section both were built from.

**The three sources, side by side (first three of thirteen; the pattern holds for all):**

| `pil_graph/vocabulary.py` | AXO `vocab.go` | `MERP-Agent-Handover.md` §6.2 |
|---|---|---|
| `RUNS_ON` | `RUNS_ON` | `runs-on` |
| `DEPENDS_ON` | `DEPENDS_ON` | `depends-on` |
| `OWNED_BY` | `OWNED_BY` | `owned-by` |

**The problem.** PIL and AXO agree with each other exactly, on every one of the 13 — this
is not the two packages drifting apart. Both independently rendered the handover's prose
names (`runs-on`, `depends-on`, …) as `SCREAMING_SNAKE_CASE` Neo4j relationship-type
literals, because that's Neo4j's own relationship-type convention and the handover's §6.2
never states a literal casing — it lists names in running prose
("`runs-on`, `depends-on`, `owned-by`, …"), not a fenced, quoted string constant the way
§6.1's node-label table does (`` `Tenant` ``, `` `Mission` ``, … — those *are* the literal
values, and all three sources agree on them character-for-character).

These are real Neo4j relationship types, written into a live graph. If a future third
implementation reads §6.2 literally and writes `runs-on` (or any other casing) as the actual
relationship type, it produces a graph neither PIL's nor AXO's queries can see — not a typo,
a silent split of the graph's edge namespace in two, findable only by an empty query result
with no error anywhere.

**Ask.** §6.2 should pin the literal string for each of the 13 edge types explicitly — the
same way §6.1 already does for the 10 node labels — rather than leaving casing to be inferred
from "this is a Neo4j edge type, so use the Neo4j convention." Two independent
implementations guessed the same way this time; that's luck, not a guarantee for whichever
implementation comes third (`gateway`, a future non-PIL/non-AXO consumer, etc.).

**Not fixed here, and no code changed.** This is a note against `MERP-Agent-Handover.md`,
which lives in `idiaz-io/merp-console`, not this repo. Filed here because the finding came
from work in `packages/graph`; whoever owns ADR-08's ratification of §6.1/§6.2 should decide
whether to amend the handover directly or note it in the ADR-08 discussion.
