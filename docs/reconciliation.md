# Reconciliation — the PIL adapter extraction against six later decisions

IDI-195. **Step 0 (the audit) plus the work it authorised.** Read the Outcome section first;
the audit below it is preserved exactly as written before any change, because a
reconciliation document whose "before" column gets edited to match the "after" stops being
evidence of anything.

Repos audited:

* `PIL` — `/Users/muhammadshabbar/Documents/MERP/PIL`, working tree, **no commits** (see
  Precondition below)
* `axo` — `/Users/muhammadshabbar/Documents/MERP/axo`, branch `handoff` @ `75ddc32`

Every claim below is a file and line someone else can open, or a command someone else can
run. Commands actually run for this audit are marked **[ran]**.

---

## Precondition — PIL has no git history

```
$ git -C PIL log --oneline
fatal: your current branch 'main' does not have any commits yet     # [ran]
$ git -C PIL status --short
?? .github/  ?? docs/  ?? packages/  ?? scripts/  ?? tests/  ...    # [ran]
```

The entire extraction is untracked working-tree files. Consequences that touch this
ticket directly:

* Definition of done items 1 and 6 ask for "a commit making it so" — not possible until an
  initial commit exists.
* D5's fallback instruction, "restore it from git history", would not be available in PIL
  if anything were lost. (It is available in `axo`, and nothing needs restoring — see D5.)
* There is no provenance for the extraction: no diff against AXO, nothing to bisect.

This is a precondition for the rest of the work, not one of the six decisions.

---

## Outcome, after the work

The audit table below is preserved as written, because a reconciliation document whose
"before" column gets edited to match the "after" stops being evidence of anything. This
section records what changed.

| # | Decision | Now | Commit |
|---|---|---|---|
| **D1** | Shapes owns four things | ✅ **Complete.** Redaction and tenancy resolution now live in `pil_contracts`; format and the version rule already did. AXO's `pil_capture` delegates, so there is one implementation rather than three. | `b1c5c6d`, `a61f82c`, axo `863a686` |
| **D2** | Config through an interface | ✅ **Complete.** `ConnectionProvider` + `FileConnectionProvider`. ADR-0008 records it and amends ADR-0005. | `ec7b958` |
| **D3** | Credentials per product | ✅ **Complete.** Keyed `(tool, tenant, product)`, no tool-level fallback, `Access` on the handle. | `ec7b958` |
| **D4** | Bus and catalogue cut; sink built | ✅ **Complete.** Four doc references cut; `pil_adapters.Sink` built. ADR-0009 amends ADR-0003, which had contradicted the scope document. | `84d129e` |
| **D5** | Rollback path | ✅ **Complete.** Nothing had been deleted. The switch now also covers the queue-driven path, and `pil` mode no longer returns the wrong `StandardAlert` shape to it. | axo `138e92c` |
| **D6** | Parity evidence | 🟡 **Machinery complete, corpus blocked.** Three false passes closed; the committed specification and `--record-golden` built. `fixtures/` is still empty and needs a production capture run. | `3d7e7aa`, `96c035a`, `e75da3d` |

**Two corrections to the audit**, both found while implementing:

1. **D5's gap was one call site, not two.** The audit said "wire the two pollers". The Fleet
   poller does not normalise at all — it inserts a raw payload into `healing_queue`
   (`fleet_poller.py:140`), and `queue_worker.py:70` hands it to `process_alert_v2`, whose
   INTAKE stage called `adapter.normalize_alert` directly (`orchestrator_v2.py:92`). One
   unwired site, and a more important one: it covers every poller-originated alert *and*
   the whole v2 pipeline.

2. **`pil` mode would have broken that call site**, exactly as `pil_shim`'s own docstring
   warned ("Any new call site must handle both shapes the same way before the switch is
   pointed at it"). The v2 pipeline reads `.message` and `.signature`, which only the
   reasoning dataclass has; the shim always built the Pydantic `StandardAlert`, which names
   the text `description`. That fails in `pil` mode only — the mode nobody exercises until
   cutover. Fixed by making the shape a parameter.

**A third finding, recorded not fixed:** AXO's `pil_shim.py` and its tests were *untracked*
working-tree files, as was all of PIL. The rollback path existed on one machine, not in the
repository. Both are now committed.

---

## The audit, as written before any changes

| # | Decision | Current state | What has to change |
|---|---|---|---|
| **D1** | Shapes owns message format, version rule, tenancy resolution, redaction | 🟡 **Half.** Format ✅ and version rule ✅ are in `pil_contracts`. Tenancy is enforced, but structurally and from `pil_adapters`, not as a function in shapes. Redaction does not exist in PIL at all — the only implementation is in **AXO**. | Move/author tenancy resolution into `pil_contracts`; write redaction in `pil_contracts` and retire AXO's copy as the source of truth. No tenancy-from-payload defect in PIL to report; AXO's are already recorded. |
| **D2** | Connection config must not live in AXO | 🟡 **No violation, deliverable missing.** PIL reads no config from AXO and cannot — enforced by test + lint. But the required interface does not exist: `AdapterConfig` has one field, `tenant_id`. | Add the connection-config interface + plain config-file implementation. Resolve against ADR-0005, which deliberately deferred it. |
| **D3** | Credentials per product, not per tool | 🔴 **Absent, not wrong.** There is no credential in the config shape at all, so nothing assumes one-per-tool. Greenfield, blocked behind D2. | Land D2's interface with per-product credential handles from the first line. Nothing to un-pick first. |
| **D4** | Cut the bus and the capability catalogue | 🟢 **Code clean**, 🟡 **docs residue**, 🔴 **sink missing.** No `pil_bus`, no catalogue module, nothing scaffolded. Four docs still name the bus as a PIL component. The sink-behind-an-interface that D4 *does* require was never built, and two docs contradict each other about it. | Delete the doc residue (DoD 5 is strict). Build the simple sink interface. Reconcile ADR-0003 vs `phase-a-scope.md:216`. |
| **D5** | AXO's adapter code stays in place, disconnected | 🟢 **Largely done — nothing was deleted.** All of AXO's adapters and normalisers are present. The three-position switch exists, defaults to `legacy`, and is read from the DB per call, so flipping needs no deploy. | Wire the two scheduled pollers, which bypass the switch entirely. Fix a source-name mismatch. Record that `pil` position is gated shut in multi-tenant use. |
| **D6** | Parity proven against captured real payloads | 🔴 **The largest gap, as predicted.** `fixtures/` is empty — zero payloads. AXO's output was never committed as the specification; it is recomputed live each run. The command exists but **returns 0 on zero fixtures**, and the CI job **goes green when skipped**. | Capture the corpus, commit AXO's output as the spec, and make both false passes impossible. Detail in D6. |

Closing tests: **none of the four have been run.** Report-only items: **all three absent**,
with two incidental ingredients. Both sections below.

---

## D1 · Shapes owns four things

**Message format — compliant.** `packages/contracts/src/pil_contracts/envelope.py`.
`Envelope` is kind-agnostic with the body keyed off `MessageKind`; `AlertBody` constrains
structure and deliberately never content (`envelope.py:100-108`), which is what I-10
requires while AXO emits `"P1"`, raw vendor severities and the literal `"unknown"` from
different paths.

**Version rule — compliant.** `pil_contracts/versioning.py`. Additive-only within a major;
`SchemaVersion.parse` is total by design and returns `UNKNOWN_VERSION` rather than raising
(`versioning.py:46-74`); `Envelope.from_dict` ignores unknown fields including those from a
future major (`envelope.py:197-233`). A missing *required* field still raises, correctly
distinguished as malformed rather than a version mismatch. Covered by
`packages/contracts/tests/test_versioning.py`.

**Tenancy resolution — enforced, but not where D1 says it belongs.**

What exists is strong, and stronger than a test: `Translation` has no tenant field at all
(`packages/adapters/src/pil_adapters/base.py:55-75`), so the base class is the only thing
that can set one, and it always sets it from the instance's own config
(`base.py:112-126`, "The only assignment of tenant_id anywhere in this package"). Backed by
`tests/test_invariants.py:146` (structural) and `:172` (seven adversarial payloads, one per
route AXO uses to smuggle a tenant out of vendor input).

The gap is ownership. D1 asks for "one function that produces the customer identity", owned
by shapes. Instead:

* `AdapterConfig` lives in **`pil_adapters`** (`base.py:31`), not `pil_contracts`.
* `pil_contracts` contributes only a non-empty check (`envelope.py:161-166`).
* There is no `resolve_tenant`-shaped function anywhere.

That matters concretely, not just tidily: `contracts` is a separate distribution *because*
QUILL takes it without adapters (`CLAUDE.md`, `packages/contracts/src/pil_contracts/__init__.py:1-7`).
As shipped, QUILL gets the envelope and **no tenancy resolution whatsoever** — it would
have to write its own, which is the divergence D1 exists to prevent.

*Tenancy read from vendor payload content?* In PIL, no — structurally impossible, proven by
the tests above. In AXO, yes, and it is already recorded rather than silently fixed:
`docs/known-differences.md` preserved defects 1–3 (`sl_poller.py:307` splits a vendor URI;
`sciencelogic/normaliser.py:143` reads an unauthenticated webhook body and falls back to
`"unknown"`; `addigy_adapter.py:58` uses an MDM **policy id** as the customer id), noted as
three of eleven sites. Correctly handled — reported, not fixed. **No action in this ticket.**

**Redaction — absent from PIL entirely.** This is the D1 finding that matters.

The only implementation lives in the product: `axo/msp-platform/backend/services/pil_capture.py`
— `_REDACT_PATTERNS` (`:67`), `redact_credentials` (`:142`), `pseudonymise` (`:150`),
`scrub` (`:160`), `_PSEUDONYM_KEYS` (`:75`). Its own comment records the drift D1 warns
about, already happening:

> `# Ported from apps/exoagent/internal/evidence/evidence.go:13-16. The Go agent has had a`
> `# redactor since it shipped; the Python side has never had one.` — `pil_capture.py:64-65`

So there are already **two** redactors in AXO alone (Go agent, Python capture) and **zero**
in shapes. "If AXO and QUILL redact differently, we leak" is not hypothetical here; it is
the current state with QUILL not yet written.

Related and worth fixing at the same time: `Envelope.raw_payload` carries the vendor payload
verbatim, unredacted, and is serialised into the message (`envelope.py:159`, `:186`).
Redaction in shapes has to cover that field or credentials travel inside every envelope.

---

## D2 · Connection config must not live in AXO

**The defect this decision guards against is not present.** PIL reads no configuration from
AXO — no DB access, no AXO config objects, nothing product-owned. It is enforced two ways
that are tested against each other for drift:

* `tests/test_invariants.py:59` walks the AST of every file in both packages and bans
  imports of `axo`, `quill`, `vigil`, `otto`, `guardrails`, `pavo`, `remi`, `backend`,
  including function-local and dynamic imports that lint cannot see.
* ruff `flake8-tidy-imports.banned-api`, asserted to hold the identical name set by
  `test_invariants.py:73`.

That satisfies definition-of-done item 3's second half ("a test fails if PIL imports from
any product"). **[ran]** `uv run pytest` — 116 passed, 1 skipped.

**The deliverable D2 asks for does not exist.** "Required now: the interface, with a plain
config-file implementation." `AdapterConfig` is:

```python
@dataclass(frozen=True, slots=True)
class AdapterConfig:
    tenant_id: str  # packages/adapters/src/pil_adapters/base.py:31-52
```

One field. No endpoint, no credential handle, no provider interface, no config-file loader.
`base.py:39-42` states the omission deliberately — Phase A translates and nothing more, so
there is nothing to authenticate to, and the connect surface is deferred with its own ADR.

**This is a genuine conflict to settle, not just a gap.** ADR-0005 scoped Phase A to
translate-only; D2 says the interface is required now. Both are defensible and they
disagree. My reading is that D2 wins on the merits — the interface is cheap now and it is
the thing that decides whether adapters can ever reach into a product — and adding an
interface plus a file loader does not breach translate-only, because nothing calls it yet.
Flagging it rather than assuming, per the ticket's rule about ambiguity with architectural
consequences.

For completeness, AXO's own adapters read config from `platform_settings` → Vault → env
(`backend/services/adapters/fleet_adapter.py:1-16`, `:31`, `_load_config` at `:53`). That is
AXO's own code staying behind `legacy`, so it is correct as-is and out of scope.

---

## D3 · Credentials are per product, not per tool

Nothing to un-pick: there is **no credential anywhere in PIL's config shape**, so the
harmful assumption D3 warns about ("one shared login per tool") was never encoded. The
decision is unimplemented rather than violated.

The intended direction is already written down and agrees with D3 — I-8, secrets are
handles and never values, and `base.py:40-42` says the connect surface "brings a secret
*handle* rather than a value". What is missing is the shape that lets AXO and QUILL hold
different handles for the same tool.

This is strictly downstream of D2. It cannot land first, and once D2's interface is being
written, doing this correctly costs nothing extra — which is exactly the "cheap today,
expensive once credentials exist in production" argument in the ticket.

---

## D4 · Cut the bus and the capability catalogue

**Code — compliant, nothing to delete. [ran]**

```
$ grep -rni "bus\b|capability|catalogue|catalog" --include=*.py PIL/
(no matches in packages/ or scripts/)
```

No `pil_bus` package, no capability-catalogue module, no scaffolding of either. ADR-0003
records the decision positively: "There is no sink, no table, no bus — `translate()`
returns an envelope to its caller" (`docs/adr/0003-message-envelope.md:20`), and it lists
routing onto a bus as considered and rejected (`:46`).

*(`axo/apps/exoagent/internal/capabilities/registry.go` is ExoAgent's own action registry —
a different thing that predates this work, inside the product, out of scope.)*

**Docs — residue remains.** Definition of done item 5 is strict: "Nothing for the bus or
capability catalogue remains in the repo." These four lines do:

| Where | What it says |
|---|---|
| `CLAUDE.md:18` | lists **bus** as one of PIL's six components — "How work moves between products, and how it rolls back" |
| `README.md:13` | `graph`, `gate`, `ledger`, `bus` — "not started" |
| `docs/adr/0001-package-naming.md:9` | reserves the name `pil_bus` |
| `docs/phase-a-scope.md:50-51` | defers "the bus beyond a trivial sink interface. The capability catalogue." |

Judgment call, flagged rather than decided: D4 says "revisit when something actually needs a
shared one", which is arguably consistent with a doc naming it as a future possibility. But
`CLAUDE.md:18` presents the bus as settled architecture, which is what D4 overturned. I
would cut the bus from the component list and the reserved name, and leave a one-line note
recording that it was cut and why.

**The part of D4 that requires building — missing.** "For Phase A, a translated message goes
to a simple sink behind an interface — a table or an in-process handoff." There is no sink
interface. And the two docs disagree about whether there should be:

* `docs/adr/0003-message-envelope.md:20` — no sink, translate returns to its caller
* `docs/phase-a-scope.md:216` — "A simple table or in-process handoff behind an interface"

D4 sides with `phase-a-scope.md`. ADR-0003 needs superseding, not just contradicting.

---

## D5 · AXO's own adapter code stays in place, disconnected

**The most important check in the ticket, and the answer is good: nothing was deleted.**

```
$ git -C axo ls-files | grep -iE "adapter|normalis"                      # [ran]
msp-platform/backend/services/adapters/base_adapter.py
msp-platform/backend/services/adapters/connectwise_adapter.py
msp-platform/backend/services/adapters/fleet_adapter.py
msp-platform/backend/services/adapters/sl1_adapter.py
msp-platform/backend/integrations/addigy_adapter.py
msp-platform/backend/integrations/fleet_healing_adapter.py
msp-platform/backend/integrations/sl1_adapter.py
msp-platform/backend/integrations/sciencelogic/normaliser.py
```

All present and reachable. **Nothing to restore from git history.** The rollback path
exists.

**The three-position switch exists and is built correctly.**
`axo/msp-platform/backend/services/pil_shim.py`:

| Position | Where | Behaviour as built |
|---|---|---|
| `legacy` | `pil_shim.py:224-225` | Calls AXO's normaliser and nothing else. **The default** — `get_mode` returns `legacy` on a missing setting, an unrecognised value, or any exception (`:95-105`). |
| `shadow` | `:244-275` | Both run; differences counted and logged; **legacy's result is returned** (`:246`, `:275`). |
| `pil` | `:229-242` | PIL's translator, mapped back to AXO's `StandardAlert` (`:165-193`). Falls back to legacy on any exception (`:240-242`). |

Configuration, not a build flag: read from the `platform_settings` table **per call**
(`:75-105`, `get_setting` at `backend/db/settings_queries.py:57`). Flipping is a row update
— seconds, no deploy, no rebuild. The docstring explains why per-call rather than cached at
import, citing AXO's existing import-time flag (`fleet_adapter.py:31`) as the pattern not to
repeat. Correct, and it is what makes shadow mode possible at all.

**Three gaps.**

1. **The switch is wired into the webhook path only.** All four call sites are in
   `backend/routes/webhook.py:80-93` (fleet, sciencelogic, connectwise, legacy). The two
   **scheduled pollers** never route through it — they only record fixtures:
   * `backend/services/fleet_poller.py:137-138` → `pil_capture.record("fleet", payload)`
   * `backend/services/sl_poller.py:631-632` → `pil_capture.record("sl1_poller", event_data)`,
     then normalises via its own `_normalise_api_alert` (`:238`, `:635`)

   So `shadow` and `pil` cover none of the scheduled traffic. This is the sharpest edge in
   the audit: D1's tenancy rule exists *specifically* because "for scheduled pollers there
   is no token", and the poller paths are exactly the ones the switch cannot see. Preserved
   defect 1 in `known-differences.md` is at `sl_poller.py:307` — inside an uncovered path.

2. **Source-name mismatch breaks the poller corpus.** `sl_poller.py:632` captures under
   source `"sl1_poller"`. PIL's `TRANSLATOR_TYPES` (`pil_adapters/registry.py:35-42`) knows
   `sciencelogic`, `sl1`, `connectwise`, `fleet`, `addigy`, `legacy` — not `sl1_poller`.
   Fixtures captured there have no translator, and `get_translator` raises `KeyError`
   (`registry.py:66-70`). The comment at `sl_poller.py:627-630` shows this was deliberate
   (two implementations, two corpora) — but PIL has no third translator to receive it, so as
   things stand those payloads cannot be compared at all. Also: `addigy` has a PIL
   translator and no shim call site anywhere.

3. **`pil` position is gated shut, deliberately and correctly.** It refuses to engage
   unless `PIL_TENANT_ID` is set, falling back to legacy with a loud error
   (`pil_shim.py:229-236`). The reason is sound and worth quoting, because it is a real
   blocker on cutover rather than a bug: AXO constructs one `FleetHealingAdapter` per
   request serving every customer, so selecting `pil` today "would attribute every message
   to a single configured tenant — collapsing all customers into one. That is worse than the
   defect being fixed" (`:21-33`). Position 3 is therefore not usable in multi-tenant
   production until per-tenant adapter instances exist. Recording it as a known constraint;
   it is not in this ticket's scope to fix.

---

## D6 · Parity proven against captured real payloads

The ticket predicted this would be the largest remaining piece. It is, and the machinery is
in better shape than the evidence.

**1 · Capture 10–20 real payloads per source — not done. Zero.**

```
$ ls -la PIL/fixtures/            # [ran]
total 0        (empty directory)
```

No payloads for any source, so no coverage of malformed fields, missing values, nulls,
unicode or oversized bodies either.

The *capture* machinery exists and is genuinely well built —
`axo/msp-platform/backend/services/pil_capture.py`, specified by
`docs/adr/0007-fixture-capture-and-scrubbing.md`: fails closed when `PIL_CAPTURE_SALT` is
unset (`:15-18`, `:259-268`), scrubs credentials and pseudonymises identifiers before
anything is written (`:160-200`), prefers novel payload structures once a source passes 300
files (`:55-61`), and never breaks ingest (`:284`). It is gated on `PIL_CAPTURE_ENABLED` in
`platform_settings` and has evidently never been switched on. Wired at three sites:
`webhook.py:60-61`, `fleet_poller.py:137`, `sl_poller.py:631`.

**2 · Run each through AXO's current code and commit the output as the specification — not
done, and the design differs from what was asked.**

There are no saved expected-output files anywhere in PIL. Instead the harness recomputes
AXO's answer live on every run, in a subprocess under AXO's own interpreter
(`scripts/parity.py:158-186` → `scripts/_axo_driver.py`). The subprocess boundary itself is
a good decision and correctly motivated — PIL's venv must not acquire pydantic/httpx/
fastapi/sqlalchemy, so the harness exchanges JSON rather than importing AXO
(`parity.py:14-18`), preserving I-3.

But live recomputation is not what D6 step 2 asks for, and the difference is not cosmetic:
**the specification becomes "whatever AXO does today."** If AXO's normalisers change, the
spec silently changes with them and parity still passes. A committed golden output is what
makes an unintended AXO change visible. Both are worth having — the golden files are the
spec, the live run additionally catches AXO drifting away from them.

**3 · One command, byte-identical or it fails, runs in CI — the command exists and proves
nothing today. Two independent false passes.**

*False pass one — zero fixtures returns success.*

```
$ make parity AXO_PATH=../axo                                      # [ran]
PIL parity harness
  AXO checkout   /Users/muhammadshabbar/Documents/MERP/axo
  comparing      every field EXCEPT tenant_id (ADR-0004)
  cases          0
No fixtures found.
EXIT=0
```

`parity.py:294-303` prints an honest explanation and returns `0`. A green parity run
currently means "no evidence gathered", not "byte-identical" — and it is the same green a
real pass produces.

*False pass two — CI skips the job and reports success.* `.github/workflows/ci.yml:62-100`.
The `parity` job first checks whether `secrets.AXO_READ_TOKEN` exists (`:68-76`); if not it
emits `::warning title=Parity not run` and sets `available=false`, and every subsequent step
is `if: steps.access.outputs.available == 'true'`. All steps skip, **the job goes green**.
The warning text says so itself — "Definition of Done item 3 is NOT satisfied until this
secret exists" — which is admirably honest and still a green check mark on the PR.

Stacked, these mean definition-of-done item 7 ("the parity command passes in CI for every
source AXO supports") currently reports as satisfied while zero payloads have ever been
compared. This is the finding I would fix first: a check that cannot fail is worse than no
check, because it is read as evidence.

*One legitimate weakening, correctly disclosed.* `tenant_id` is excluded from the comparison
(`parity.py:66`, `EXCLUDED_FIELDS`) because PIL takes the tenant from config while AXO reads
it from the payload — the single intentional difference, recorded in ADR-0004 and in
`docs/known-differences.md`, and printed on every run so the weaker claim cannot be mistaken
for a full match (`parity.py:287-288`). PIL's tenant is separately asserted to equal the
configured one, and an I-5 violation fails the run (`parity.py:244-250`). This is sound. It
does mean "byte-identical" is one field short of DoD 7's literal wording, which should be
stated explicitly in the PR rather than left to a reader of the script.

Also worth noting in PIL's favour: determinism is handled properly. `TZ=UTC` is pinned for
the harness process itself before anything reads a clock, not only for AXO's subprocess
(`parity.py:39-47`) — the comment records that setting it only for the subprocess was a real
bug found by an epoch fixture. Both sides share one frozen instant (`:59`). Without this,
"byte-identical" would not be claimable at all, given preserved defects 4 and 5.

---

## The four tests that close this out

Status after the work. Three of the four need a running deployment and are honestly not run
rather than approximated.

| Test | State | Note |
|---|---|---|
| 1 · **Parity** passes for every source, in CI | 🟡 **Can now fail; cannot yet pass** | The three false passes are closed (`3d7e7aa`, `96c035a`, `e75da3d`) and `make parity` exits 1 today. It cannot pass until the corpus exists, which is correct: passing would mean holding evidence. The machinery is proven against AXO's real normalisers — 9/9 on `--demo`, and 15 harness tests including one that tampers with a committed specification and asserts the run fails. |
| 2 · **Shadow** shows zero differences on real traffic | 🔴 **Not run** — needs production | Now possible on the paths that matter: before `138e92c` the switch saw only `routes/webhook.py`, so shadow was blind to all scheduled traffic. Two caveats to record with any result: `shadow_stats()` counts are in-process and reset on restart (`pil_shim.py:54`), so a "full business cycle" claim needs the log lines aggregated, not the counter; and PIL's tenant is excluded from the comparison by design (ADR-0004). |
| 3 · **Break it** — rename a symbol in PIL, confirm AXO breaks | 🔴 **Not run** — needs a test environment | **The precondition must be recorded with the result.** In `legacy` mode AXO never imports PIL: `_translate_with_pil` imports `pil_adapters` inside the function body (`pil_shim.py`), reached only under `shadow`/`pil`. Since `legacy` is the default, renaming a PIL symbol breaks nothing — so run this with the switch in `shadow` or `pil`, or it gives a false pass. The ticket calls this the one test that cannot lie; as the code stands it can, and that is worth knowing before someone runs it. |
| 4 · **Rollback** — flip to `legacy`, no deploy | 🔴 **Not run** — needs a deployment | Mechanism reads correctly and is now unit-tested: per-call `platform_settings` read, `legacy` on any doubt, `legacy` on an unrecognised value, and `legacy` if PIL raises (`tests/test_pil_shim.py`, 19 passed). Still needs demonstrating on a real deployment rather than inferring from tests. |

---

## Report only — do not build

| Item | Status |
|---|---|
| **Degradation reporting** | **Absent from PIL; nothing incidental.** No "I am running degraded" facility in either package. AXO has `apps/exoagent/internal/heartbeat/heartbeat.go`, but that is agent liveness, not a product-level degraded signal — it does not satisfy the invariant. |
| **Idempotency** | **Absent as a facility; two ingredients exist incidentally.** `Envelope.content_hash()` (`pil_contracts/envelope.py:192`) gives a stable identity for a message, and AXO's capture already dedupes by content and structure hash (`pil_capture.py:207`, `:229`). Neither answers "have I already processed this?" — there is no processed-set and no store. |
| **Test doubles** | **Partial, and the drift has already started.** PIL ships `FrozenClock` (`pil_adapters/clock.py:41`) and nothing else; there is no fake gate, ledger or graph, because those components do not exist yet. Meanwhile AXO has written its own fake adapter (`apps/exoagent/internal/adapters/fake/fake.go`) — precisely the "each product writes its own and they drift" outcome, one product in. |

Two of the three moved slightly as a side effect of building D2 and D4, which is worth
recording so nobody counts them as done:

- **Test doubles** — PIL now also ships `StaticConnectionProvider`, `CollectingSink` and
  `NullSink`. These are doubles for the interfaces that exist, so each product does not write
  its own. The fake gate, ledger and graph are still absent because those components are not
  built. Not built in this ticket, per instruction.
- **Idempotency** — no change. `Envelope.content_hash()` still gives a stable identity and
  capture still dedupes by content and structure hash, but there is no processed-set and no
  store, so the question "have I already processed this?" still has no answer.
- **Degradation reporting** — no change. Still absent, still nothing incidental.

---

## What was done

Nine commits in PIL, two in AXO, one idea each.

| Commit | Decision |
|---|---|
| `21afa97` | Baseline — the extraction as it stood, no edits |
| `bbeff5a` | The audit above |
| `3d7e7aa` | D6 — parity cannot pass without evidence |
| `b1c5c6d` | D1 — redaction into shapes |
| axo `863a686` | D1 — `pil_capture` delegates to it |
| `a61f82c` | D1 — tenancy resolution into shapes |
| `ec7b958` | D2, D3 — connection interface, per-product credentials |
| `84d129e` | D4 — sink built, bus cut |
| axo `138e92c` | D5 — switch covers the scheduled paths |
| `e75da3d` | D5, D6 — out-of-scope sources skipped loudly |
| `96c035a` | D6 — the committed specification |

Commands, all runnable:

```bash
cd PIL
uv run pytest                                             # 243 passed, 1 skipped
uv run ruff check . && uv run ruff format --check .       # clean
uv run mypy                                               # clean, 20 files
make parity AXO_PATH=../axo                               # exits 1 — empty corpus
uv run python scripts/parity.py --axo-path ../axo --demo  # 9/9 against AXO's own
uv run pytest tests/test_parity_harness.py                # 15 passed

cd ../axo/msp-platform
.venv/bin/python -m pytest tests/test_pil_shim.py tests/test_pil_capture.py   # 39 passed
```

### Two decisions taken, both confirmed before implementing

1. **D2 vs ADR-0005.** ADR-0005 deferred the connect surface; D2 said the interface was
   required now. Built it, and ADR-0008 *amends* rather than supersedes: an interface with
   no caller is not a connect surface, and nothing here connects to anything.
2. **DoD 5 strictness on D4.** Cut all four bus references, leaving one line in each place
   recording that D4 cut it and why — the history is worth keeping precisely so nobody
   rebuilds it.

### AXO defects found and recorded, not fixed

Per the ticket's rule. Beyond the six already in `known-differences.md`:

- `tests/test_circuit_breaker.py` and `tests/test_remediate.py` do not collect on `main`.
  Both import `MAX_ACTIONS_PER_HOUR` from `backend.services.circuit_breaker`, which defines
  `DEFAULT_MAX_ACTIONS_PER_HOUR`. Pre-existing, unrelated to this ticket.
- `tests/test_classify.py` (3) and `tests/test_end_to_end.py` (1) fail whenever a real
  `ANTHROPIC_API_KEY` is present: they assert on hardcoded classifications and get live model
  output instead. Verified pre-existing — identical failures at `75ddc32` with the same
  `.env`, in a clean worktree.
- The six entries in `known-differences.md` still say `_to file_` in the ticket column. They
  need real numbers before Phase A closes.

### What remains

One thing, and it needs production access rather than code:

**The corpus.** `fixtures/` is empty. It needs `PIL_CAPTURE_ENABLED`, `PIL_CAPTURE_SALT` and
real traffic through AXO. Everything downstream of it is built and tested — `fixtures/README.md`
has the exact steps. Until then `make parity` fails honestly rather than passing vacuously,
which is the change that makes the remaining gap visible instead of invisible.

Closing tests 2, 3 and 4 need a deployed environment and are recorded as not run, with the
preconditions each requires. Test 3's precondition matters most: it only means something with
the switch in `shadow` or `pil`, because in `legacy` AXO never imports PIL at all.
