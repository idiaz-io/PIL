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
