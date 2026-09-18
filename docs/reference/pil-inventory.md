# PIL inventory — what actually exists, read from the code

**Source:** `https://github.com/idiaz-io/PIL`, cloned read-only to `/tmp/PIL` for this
inventory (not vendored into this repo — see CLAUDE.md §1.3, "PIL never depends on a
product" runs the other direction too: this console must not depend on PIL's source tree).
Commit read: `5530434` (`main`), 2026-09-08.

**Method.** Every claim below was checked against the code, not the filenames or the
docs' own summary of themselves: all 20 source files in `packages/contracts/` and
`packages/adapters/` were read in full, all 9 ADRs and all 5 top-level docs were read in
full, and the test suite was actually installed and run (`uv sync --python 3.12 && uv run
pytest`, `uv run ruff check .`, `uv run mypy`) rather than assumed from `docs/`. Results:
**121 passed, 11 skipped, 0 failed. Lint clean. Typecheck clean.** The 11 skips are named
below — they are not hidden failures.

---

## 1. Is there a running service, or only library code?

**Only library code. There is no service, no gateway, and none is planned.**

This is not a gap to fill in later — it's a stated, enforced architectural decision:

- PIL's own `CLAUDE.md`: *"PIL is a library, not a service. Products `import` PIL.
  Nothing sends PIL a request. There is no PIL server, no PIL endpoint, no PIL gateway,
  no PIL container."* Repeated as invariant **I-1**: *"No HTTP surface. No long-running
  PIL process. Products import it."* And again, as a standing instruction to whoever
  works in the repo next: *"If a task seems to require an HTTP endpoint in PIL, stop and
  ask. The answer is almost always that the endpoint belongs to a product, not to PIL."*
- Mechanically enforced, not just written down: `tests/test_invariants.py:133` bans
  importing `fastapi`, `flask`, `django`, `starlette`, `uvicorn`, `socket`, or
  `socketserver` anywhere in either package, and that test passes today. A repo-wide
  grep for the same terms turns up nothing in `packages/` — the only hits are in
  `scripts/_axo_driver.py` and `scripts/parity.py`, which explain in comments that
  *AXO's* dependencies (`pydantic`, `httpx`, `fastapi`, `sqlalchemy`) are unavailable in
  PIL's own virtualenv on purpose.
- No `.github/workflows/` step deploys anything — CI (`.github/workflows/ci.yml`) runs
  `ruff check`, `ruff format --check`, `mypy`, and `pytest`. Nothing else. No
  Dockerfile, no k8s manifest, no `Procfile`, anywhere in the repo.
- What ships is two installable Python **distributions** — `pil-contracts` and
  `pil-adapters` (`packages/*/pyproject.toml`) — meant to be `pip install -e` **into a
  product's own process** (README's "Installing PIL into a product" section spells out
  the exact `uv pip install -e ../PIL/packages/...` commands for AXO). There is nothing
  to point a URL at.

### This directly conflicts with what this console's `CLAUDE.md` assumes

This repo's own `CLAUDE.md` — the one governing `merp-console` — refers to
`pil/gateway` as something the console talks to, "never a product directly." **No such
gateway exists in the PIL repo, and PIL's own governing document says building one is
almost certainly the wrong move if anyone is ever tempted to.** This is a real
disagreement between two documents this project treats as authoritative, not a detail
either side got around to. Options, concretely:

- **The gateway is a product's job, not PIL's** — i.e. the console would eventually talk
  to an endpoint AXO (or another product) exposes, which itself imports PIL, rather than
  to "PIL" as a network peer. This reading is consistent with everything else in the PIL
  repo and is the most likely resolution.
- **"pil/gateway" in this console's `CLAUDE.md` predates PIL's actual build** and was
  written when PIL's shape was still assumed rather than read — plausible, since
  `CLAUDE.md`'s own §1.6 already flags one other place ("ADR-17") where this repo's
  documents describe something that turned out not to exist elsewhere.

Either way: **there is nothing at any URL to wire the Connections screen to today.**
Whatever "connect Connections to the backend" means next, it cannot mean "call PIL" —
PIL has no callable surface. It would mean either (a) writing directly against whatever
store the eventual connect/credential surface uses once it exists (not yet — see §2),
or (b) calling a product's own API once one exposes connection state, or (c) treating
this as blocked pending a human decision on where the gateway (if any) actually lives.
This is worth a direct answer from a human before any code is written, not an assumption
either of us makes.

---

## 2. What do the adapters actually do? (Fleet and ScienceLogic specifically)

**Translation only — turning a vendor payload already in hand into an `Envelope`.
Nothing connects, authenticates, or fetches anything from a vendor anywhere in this
repo.** This is scoped explicitly, not an accident of what's been built so far:

> ADR-0005: *"Phase A migrates the **inbound translate** surface and nothing else.
> `connect`, `execute_on_device`, `check_connectivity`, `fetch_device_details` and the
> `verify_*` methods stay in AXO and are deferred... Only `normalize_alert` is real
> [in AXO]. Every other method... branches on `self._demo`."*

Concretely, `pil_adapters.base.Translator.translate()` (`base.py:120-142`) takes a
`Mapping` (a payload someone else already received) and returns an `Envelope`. It is
**not async**, does no I/O, and opens no connection. There is no adapter method anywhere
in `pil_adapters` that reaches out to Fleet, ScienceLogic, or anything else.

### Fleet (`translators/fleet.py`, 118 lines, full read)

- Input: a Fleet policy-violation payload, possibly batched under `failing_policies`.
  Only the **first** entry is used; the rest are silently dropped
  (`fleet.py:74-78`, "faithful reproduction" of `fleet_healing_adapter.py:116-119`).
  `raw_payload` on the resulting envelope holds that unwrapped first policy, not the
  original batch — another preserved quirk (line 151 of the AXO source).
- Category is a 9-way keyword match on the policy name (`classify_policy`,
  `fleet.py:35-56`): `security` (filevault/encrypt/bitlocker, *and* antivirus/edr),
  `disk`, `software`, `cpu`, `memory`, `network`, `certificate`, else `compliance`.
- Severity: `P2` if the policy name contains any of `critical, encrypt, filevault,
  disk, antivirus, edr`, else `P3`. That's the entire severity model — two levels.
- **Credentials: none of this reads or resolves one.** The line that loads Fleet's API
  credentials in AXO (`await self._ensure_config()`, original line 113) is explicitly
  *not* ported — the module docstring says so directly, because it "has no effect on
  the translation." Nothing in `fleet.py` imports `pil_adapters.connection`.
- This is the **one** vendor where AXO's own adapter is fully real (not demo-gated),
  and per ADR-0005 it had **no tests at all** before this port — "the first coverage
  that logic has had."

### ScienceLogic — **two separate, disagreeing translators, both kept**

CLAUDE.md §1.8 already warns SL1 plays two unrelated roles in this project (external
tool vs. permission-design reference); PIL adds a third distinction worth knowing:
**there are two different SL1 translations inside PIL itself**, ported from two
different AXO code paths that already disagreed with each other before PIL existed.

- **`sciencelogic`** (`translators/sciencelogic.py`, 205 lines) — the webhook path,
  ported from AXO's *best-tested* code (`normaliser.py`). Severity: SL1's numeric
  0–5 (and the words `healthy/notice/minor/major/critical/emergency`) mapped to
  `P4/P4/P3/P3/P2/P1` (`SL_SEVERITY_MAP`, lines 24-38). Category: an 18-entry keyword
  map, tried three ways in order — exact match, substring of the category field,
  substring of the description — landing on `unknown` only if all three miss
  (`normalise_category`, lines 78-96). Every field read from the payload uses `or`-chain
  fallbacks (`raw.get("severity") or raw.get("priority") or ...`), which the module's own
  comment warns against "tidying" into the different style ConnectWise uses.
- **`sl1`** (`translators/sl1_healing.py`, 89 lines) — the *healing-adapter* path,
  ported from a different AXO file (`sl1_adapter.py`). A **different, smaller**
  severity map (`{"1":"P1","2":"P2","3":"P3","4":"P4","critical":"P1"}` —
  note `critical` lands on **P1** here vs. **P2** in the webhook translator, a real,
  documented disagreement, not a bug to reconcile) and category derived from
  **message text keywords** (`classify_message`) rather than from a category field at
  all — `cpu/memory/disk/service/certificate/network/apppool/general`.
- Both translators redirect the payload's claimed tenant (`client_id`/`org_id`/
  `organization`) into `tenant_hint` rather than `tenant_id` — see §3 on why, and note
  it is evidence, never identity: nothing may authorize or route on it.
- **Credentials: same as Fleet — none.** Neither SL1 translator imports the connection
  module. AXO's own SL1 execute/verify paths are demo-gated unconditionally
  (`orchestrator_v2.py:55,61`, quoted in ADR-0005), so there was nothing real to port
  even if Phase A's scope included it.

### Credential handling, generally (not adapter-specific)

**The interface exists; nothing behind it does yet.** `pil_adapters/connection.py`
(425 lines, full read) ships `ConnectionProvider` (abstract), `ToolConnection`,
`CredentialHandle`, `FileConnectionProvider` (reads a JSON file once at construction),
and `StaticConnectionProvider` (in-memory, for tests). A credential is a *handle* —
`store` (`vault` or `environment`) + `name` + `access` (`read_only`/`read_write`) —
never a value; a config file containing an actual `password`/`secret`/`value` key is
rejected at load time (`connection.py:_connection_from`, "I-8: secrets are handles,
never values"). **Nothing resolves a handle to a secret.** ADR-0008 says so explicitly:
*"Not shipped now: ... any code that resolves a handle to a secret value."* No file in
either package calls anything that looks like `resolve_secret`, and a test asserts that.

**Retry, backoff, rate limiting: absent, and explicitly not "yet to migrate" — there was
nothing to migrate.** ADR-0005: *"There is exactly one retry loop in the entire
integration surface... linear 30s, connection errors only, ignores 429 and 5xx. No
`tenacity`, no `backoff`, no rate limiting, no dead-lettering... two of the four words in
'connect + translate + retry + registry' describe new construction, not a lift."*

---

## 3. Do the concepts match this console's ERD?

Partial agreement on shape, real disagreement on the two things that would matter most
for wiring a schema to this backend: **how a credential is keyed**, and **what "adapter"
means as a set of values**. Read against `docs/erd/merp-substrate.mmd` and
`docs/erd/product-entitlement.mmd`.

### Where they agree

- **"A credential is a reference, never a value"** — independently arrived at, on both
  sides, in almost identical words. This console's `CREDENTIAL_REFS.uri` is commented
  *"vault://acme/fleet/api - never the value"*
  (`merp-substrate.mmd:294-301`); PIL's `CredentialHandle` is `store` + `name`, with a
  constructor guard rejecting anything that looks like an actual secret
  (`connection.py:110-124`). Same idea, arrived at twice. Worth treating as validated,
  not coincidental.
- **One adapter module per vendor tool** is the same idea on both sides: this console's
  `ADAPTERS` table (one row per vendor) vs. PIL's `TRANSLATOR_TYPES` dict (one class per
  vendor, `registry.py:26-33`).
- **Read/write as the axis that matters for risk** appears on both sides — this
  console's `CAPABILITIES.risk` (`read | write`) and PIL's `Access`
  (`read_only | read_write` on a `CredentialHandle`) — but see below: these are not the
  same vocabulary wired to the same thing.

### Where they conflict

1. **Credential keying — the one that matters most.** This console's ERD keys a
   credential by tenant alone: one `CONNECTIONS` row per `(tenant_id, adapter_key)`
   (`merp-substrate.mmd:272-282`, no product dimension anywhere on `CONNECTIONS` or
   `CREDENTIAL_REFS`), so one Fleet connection per tenant, full stop. **PIL's
   `ConnectionProvider` is keyed `(tool, tenant_id, product)`, on purpose, and ADR-0008
   argues at length against exactly the one-credential-per-tool shape this console's
   ERD currently has**: *"QUILL reads compliance evidence and must never change
   anything. AXO remediates and needs write access. With one credential per tool, QUILL
   holds AXO's — and the failure is silent. Nothing errors... QUILL is simply able to do
   things it should never be able to do."* If PIL's connect surface is ever built to
   this design (nothing says it will be — see §1 on the gateway question — but this is
   the one substantive design PIL has for it), this console's current `CONNECTIONS`
   shape cannot express "QUILL gets read-only Fleet, AXO gets read-write Fleet" without
   a schema change. Worth resolving **before**, not after, wiring anything real.
2. **The adapter catalogue itself disagrees.** `ADAPTERS.key` is commented with the
   example set `fleet | sciencelogic | anthropic | slack | connectwise`
   (`merp-substrate.mmd:246-253`). PIL's actual set is `sciencelogic, sl1, connectwise,
   fleet, addigy, legacy` (`registry.py:26-33`) — no `anthropic`, no `slack`; PIL adds a
   second, distinct `sl1` entry and a real, tested `addigy`. Neither list is a subset of
   the other. This lands directly on this console's own already-open question (§6 #4,
   "orphan capabilities... `[C]` drops the GitLab connection entirely" and "`[C]` also
   drops Addigy") — **PIL confirms Addigy is real, ported, and tested**, which is
   evidence for resolving that question in Addigy's favor rather than dropping it.
3. **`max_classification` has no PIL counterpart.**
   `ADAPTER_CAPABILITIES.max_classification` ("highest tenant classification this
   PROVIDER may serve", `merp-substrate.mmd:266-270`) — CUI/ITAR-awareness — does not
   exist anywhere in PIL. No `Classification` concept in `pil_contracts` refers to
   tenant classification at all (`redaction.py`'s `Classification` enum is about
   *payload field* sensitivity — `PUBLIC/INTERNAL/CONFIDENTIAL/SECRET` — a completely
   different axis, same name, easy to confuse). This is the same open gap CLAUDE.md §6
   #7 already names for `llm.infer`; PIL doesn't resolve it — Phase A hasn't reached a
   surface where it would matter yet.
4. **This console's whole grant/gate vocabulary has no PIL counterpart, because that
   component doesn't exist yet.** `CAPABILITIES` (with `risk`/`requires_signature`),
   `GRANTS`, `PENDING_REQUESTS`, `GATE_DECISIONS` (`product-entitlement.mmd:90-172`) all
   describe what this console's own `CLAUDE.md` calls the **policy gate** — which is
   PIL's planned `gate` component. PIL's README states plainly: *"graph, gate, ledger —
   not started."* There is no code, no ADR, nothing to compare against. This isn't a
   disagreement, it's a component that is entirely absent — the console's ERD is ahead
   of PIL here, not behind it.
5. **`INGEST_SETTINGS` (hosts/software/poll/log toggles) has no PIL counterpart.**
   PIL's only `MessageKind` is `alert` (`envelope.py:41-47`, "Extend by adding
   properties to a body, never by adding a member here"). The CMDB/inventory-sync path
   — the thing `INGEST_SETTINGS` actually configures — was explicitly deferred out of
   Phase A to an unscheduled "Phase B" (ADR-0005, "Migrate the inventory path instead...
   Deferred"). Today PIL only translates alert-shaped events, nothing device-inventory
   shaped.
6. **`tenant_hint` has no ERD counterpart**, minor but worth a line: PIL's `Envelope`
   carries what the vendor payload *claimed* the tenant was, kept only as evidence
   (`envelope.py:87-96`, ADR-0004). Nothing in this console's schema has anywhere to put
   that if shadow-mode reporting on tenant-attribution accuracy ever becomes something
   the console surfaces.

---

## 4. Is there an API contract to generate a client from?

**No. There is no OpenAPI spec, no protobuf, no schema registry, and no generated-client
tooling anywhere in this repo** — checked directly: no `.proto` file, no
`openapi.yaml`/`.json`, no `swagger` anything, in the full file listing.

The closest thing to "a contract" is the `pil_contracts` Python package itself — plain,
frozen dataclasses (`Envelope`, `AlertBody`, `TenantHint`, `SchemaVersion`) with explicit
`to_dict()`/`from_dict()` methods and a written compatibility rule (ADR-0002:
additive-only within a major version, unknown fields ignored, a missing *required* field
raises). This is deliberately **Python-only, in-process** — ADR-0006 says so directly:
*"Python only for now. Add TypeScript when Guardrails becomes real work, not before."*
There is no wire format to generate a client from, because nothing is ever put on a
wire: I-1 forbids an HTTP surface, so "the contract" is the shape of a Python object one
piece of code hands directly to another piece of code in the same process.

**Practical consequence for this console:** there is nothing to generate a TypeScript
client from today, and generating one presumes a network boundary that PIL's own
architecture explicitly rules out. If the Connections screen ever needs PIL-shaped data,
it will come from a *product's* own API (one that itself imports PIL), never from PIL
directly — see §1.

---

## What's implemented, what's stubbed, and what's absent

**Implemented — real code, tested, passing (121 tests, `ruff check` clean, `mypy` clean,
verified by actually running them, not by reading `docs/`):**

- `pil_contracts`: the envelope (`Envelope`/`AlertBody`/`MessageKind`/`TenantHint`),
  schema versioning (`SchemaVersion`, additive-only rule), canonical JSON + SHA-256
  hashing, redaction/classification/pseudonymisation, tenancy resolution
  (`resolve_tenant`, refuses everything but a token claim or adapter config).
- `pil_adapters`: the `Translator`/`AdapterConfig`/`Translation` base, the clock
  abstraction, the registry (all 6 sources), the `Sink` interface and its three
  implementations, and the `ConnectionProvider` interface with two implementations
  (config shape only — see below).
- **Six translators, fully ported from AXO and under test:** `sciencelogic`, `sl1`,
  `connectwise`, `fleet`, `addigy`, `legacy`.

**Stubbed — the interface exists, nothing behind it is real yet:**

- Credential resolution. The shape (`CredentialHandle`, keyed `(tool, tenant, product)`)
  exists; nothing anywhere resolves a handle to an actual secret, and no translator
  calls the connection module at all yet.
- The parity harness (`scripts/parity.py`, `make parity`). Built, but has **never
  actually run** — it needs a sibling `../axo` checkout that isn't present anywhere;
  confirmed by actually running the suite: 10 of the 11 skips are parity-harness tests
  refusing to run for exactly this reason.
- The fixture corpus (`fixtures/`). Empty except a `README.md` explaining why. Per
  `docs/reconciliation.md`'s own outcome table: *"🟡 Machinery complete, corpus
  blocked... needs a production capture run"* in AXO, which hasn't happened.

**Absent — no code, not started, not merely deferred to "later" in the sense of
half-built:**

- Any HTTP surface, server, gateway, or deployment configuration, anywhere. (§1)
- `graph`, `gate`, `ledger` — the README states this outright: *"not started."* This
  means this console's entire grant/gate/policy vocabulary (§3, point 4) has nothing to
  connect to yet, full stop, regardless of what other decisions get made.
- `connect`, `execute_on_device`, `check_connectivity`, `fetch_device_details`,
  `verify_*` — deferred out of scope by ADR-0005, for every adapter, no exceptions.
- The CMDB/inventory-sync path — deferred to an unscheduled "Phase B."
- Any tenant-classification (CUI/ITAR) awareness.
- The bus and the capability catalogue — **cut**, not deferred (ADR-0009 is explicit
  that "cut" and "deferred" are different things and the docs were rewritten so neither
  reads as pending work).

---

## What this means for "connect Connections to the backend"

Before any code: **there is currently nothing running to connect to.** PIL is a library
with no deployed instance, no endpoint, and an explicit, enforced design rule against
ever having one. The two most consequential open questions, in order:

1. **Where does "the backend" actually live?** Not PIL itself (§1) — either a product
   that imports PIL and exposes its own API, or this is blocked pending that product
   existing and being reachable. This is a decision for a human, not something to infer
   from either repo's code.
2. **If/when a real connect surface arrives, does this console's `CONNECTIONS` /
   `CREDENTIAL_REFS` schema need to grow a `product` dimension** to match PIL's
   `(tool, tenant, product)` keying (§3, point 1) — before data is migrated into it, not
   after.

No code was changed in either repo to produce this document.
