# PIL — Agent Constitution

**Repo:** `idiaz-io/PIL` (local checkout: `~/pil`, lowercase — see §7 on why). **Branch:** `dev`.

PIL is the shared floor under every MERP product — the substrate `merp-console` calls "the
floor" in its own `CLAUDE.md`. This repo builds PIL itself: two of six components exist
today (`contracts`, `adapters`), both translate-only, both real and tested. Nothing else is
started.

---

## 0. Hard rules, before anything else

- **PIL is a library. It will never have an HTTP surface.** No server, no endpoint, no
  gateway, no container, no long-running process — ever, not just "not yet." This is
  invariant I-1, and it exists because MERP requires that no state-changing write can bypass
  the policy gate; a library enforces that by not compiling if you skip it, a network service
  only enforces it by convention that erodes. **If a task seems to need an HTTP endpoint in
  PIL, stop and ask** — the answer is almost always that the endpoint belongs to a product.
- **Report before building.** Every good outcome in this project came from an inventory or a
  proposal read before code was written. Read the relevant doc, say what you found, propose
  before you implement.
- **Verify against the running system, not a function you read.** For a pure library with no
  deployment, "running system" means: actually `uv sync && uv run pytest`, actually run
  `ruff`/`mypy`, actually check what a module does by importing it — never a claim sourced
  from `docs/` or from reading a function and assuming it behaves as documented. The test
  suite's real pass/fail/skip count is **environment-sensitive**: whether a sibling `../axo`
  checkout happens to exist, and whether its `.venv` is built, changes which
  `tests/test_parity_harness.py` cases skip cleanly versus crash (a real bug found this way —
  `run()`'s `int(exc.code or 0)` assumes `SystemExit`'s code is always int-like; it isn't when
  `parity.py` raises `SystemExit(f"...")` with a message). Don't trust a cached number from an
  earlier session; rerun it.
- **PIL never depends on a product, ever, in any direction.** `import axo`, `import quill`,
  or anything from AXO's `backend` package anywhere under `packages/` is a defect, not a style
  issue. Enforced twice — a ruff banned-api rule (static) and an AST-walking test that also
  catches dynamic/function-local imports (`tests/test_invariants.py`) — checked against each
  other so the two lists cannot silently drift apart.
- **Behaviour-preserving migration, not a rewrite (I-10).** When code moves from AXO into PIL,
  output must be **identical**, proven against real captured payloads — not "equivalent,"
  proven by reading the code and agreeing it looks right. Where AXO's existing behaviour is
  wrong, do not fix it while moving it — record it in `docs/known-differences.md` with a
  ticket, keep the parity test asserting the current (wrong) behaviour, fix it as a separate
  change. Mixing a fix into a migration makes both unreviewable.
- **Write the ADR before the code**, for anything with architectural consequences: a new HTTP
  surface, a new node/edge/action-class/kind, an ambiguous tenant, PIL importing a product, or
  AXO's current behaviour being ambiguous enough that you're tempted to just pick. Short is
  fine — decision, alternatives, reason, a paragraph each. Nine exist in `docs/adr/`; read the
  relevant one before assuming a question is still open.

---

## 1. Ground truth — the six components, scored

The architecture (`docs/reference/MERP — System Architecture.pdf`) draws PIL as **"the
floor"** with six components, compiled into every product rather than called across a
network, sitting between products and four stores (ITKG, ledger store, knowledge vault, event
queue) that nothing queries except through PIL. The **API Gateway is drawn outside PIL**, its
own box between clients and the products — enforcing auth, tenancy scoping, rate limiting,
request audit. That gateway does not exist anywhere, in PIL or otherwise, and PIL's own
governing documents are explicit that building it would almost certainly be the wrong move for
PIL specifically (§4).

| # | Component | State, verified | Where |
|---|---|---|---|
| 1 | **Shared shapes** | **Real.** Envelope, versioning, canonical serialisation, redaction, tenancy resolution. Zero dependencies, Python stdlib only. | `packages/contracts` |
| 2 | **Adapter framework** | **Partial, translate-only.** Six translators ported and tested (`sciencelogic`, `sl1`, `connectwise`, `fleet`, `addigy`, `legacy`). `connect`, `execute_on_device`, `check_connectivity`, `fetch_device_details`, `verify_*` are explicitly deferred (ADR-0005) — nothing in this repo opens a socket. | `packages/adapters` |
| 3 | **Policy gate** | **Real (reference implementation; no `safe-auto-heal`, no ledger write).** Interface + `ReferenceGate` + `StaticGate` test double. Decisions are `allow` / `hold` / `deny` with the console's four tiers; `decide()` is pure. | `packages/gate`, ADR-0013 |
| 4 | **Sealed ledger** | **Absent.** Same story — `merp-console` has a real HMAC-chained, append-only ledger in SQL, PIL has none. | — |
| 5 | **Graph access path** | **Absent.** No ITKG code, no tenant-scoped query library, nothing. | — |
| 6 | **Bus + orchestrator** | **Cut, not merely unstarted — a real distinction.** IDI-195 D4 killed the bus and the capability catalogue deliberately: zero consumers, AXO already has its own queue, and a naming convention does what a catalogue would at two products. Four docs that presented the bus as settled architecture were rewritten so none of them do. What replaces it for Phase A is `pil_adapters.Sink` — one method, `emit(envelope)`, three implementations (`NullSink`, `CollectingSink`, `RedactingSink`) — an in-process handoff a translator's caller uses, that a translator itself never imports. | `packages/adapters/src/pil_adapters/sink.py`, ADR-0009 |

**"Cut" vs. "absent" is a real distinction, worth keeping straight.** Gate, ledger and graph
are absent because nobody has started them — they may still be built roughly as drawn. The
bus is absent because it was actively decided against, with reasons, and rebuilding it
requires overturning that decision (a new ADR), not just getting around to it.

**Products that consume PIL:** AXO, QUILL, Vigil, Otto, Guardrails, Pavo, Remi — seven, per
the architecture diagram and `merp-console`'s pricing page. Only AXO exists and is live.
None of the others import PIL today; there is nothing to consume yet beyond contracts'
envelope shape.

---

## 2. The invariants

Canonical copy: `docs/invariants.md`. If this file and that one ever disagree, that file is
right and this one needs patching.

| # | Rule | Enforced by |
|---|---|---|
| I-1 | PIL is a library. No HTTP surface, no long-running process. | `tests/test_invariants.py` bans `fastapi`/`flask`/`django`/`starlette`/`uvicorn`/`socket`/`socketserver` anywhere in either package — an import walk, not a grep, so a function-local or dynamic import is still caught. |
| I-2 | One consumer means not shared — it belongs to the product, not PIL. | Judgement only. No mechanism; a review question every time. |
| I-3 | PIL never depends on a product. | ruff `flake8-tidy-imports.banned-api` (static) + an AST-walking test (dynamic/function-local imports too) — the two lists are asserted equal to each other so they can't drift apart. |
| I-4 | Products never call each other. | Follows from I-1 and I-3: PIL offers no transport, so it cannot provide one. No direct mechanism. |
| I-5 | Tenant identity is never taken from input — request-driven work takes a validated token claim, scheduled work takes the adapter instance's own configuration. Never the vendor payload. | Structural: `Translation` has no tenant field at all, so a translator has nowhere to put one — the base class is the only code that ever sets `tenant_id`, always from config. Backed by a test with seven adversarial payloads trying every route AXO uses to leak a tenant from input. |
| I-6 | Vocabularies are closed — `MessageKind`, `TenantSource`, `SecretStore`, `Access`, `Classification` are all `StrEnum`s. Extend by adding a property, never a member; a new member is an ADR. | Enum + explicit `raise` on an unknown value in every parser (`Envelope.from_dict`, `SchemaVersion.parse` is the one exception — see I-7). |
| I-7 | Message shapes are versioned from the first line of code. A v1 consumer must not crash on a v2 message. | `SchemaVersion.parse` is total — an unparseable version becomes `UNKNOWN_VERSION`, never an exception. `Envelope.from_dict` ignores unknown fields. A missing *required* field still raises (malformed, not a version mismatch). |
| I-8 | Secrets are handles, never values. | `CredentialHandle` holds `store` + `name`, not a value; a config file with a literal `value`/`secret`/`password` key is rejected at load, and a handle whose *name* looks like a PEM body or long token is rejected too. Not yet fully applicable — nothing resolves a handle to a secret yet; arrives with the connect surface. |
| I-9 | Deterministic serialisation — anything later hashed or signed must serialise byte-identically every time. | Canonical JSON, pinned by a golden test that itself requires an ADR to change. `format_timestamp` rejects naive datetimes rather than assuming UTC. |
| I-10 | Behaviour-preserving migration — identical output, proven against real payloads, not "equivalent." | The parity harness: byte-identical or it fails, in CI, over every captured fixture. |

I-2 has no mechanism deliberately — "does more than one product need this?" is a question
for review, not something a test can answer.

---

## 3. Files in this repo, and how much to trust each

| Path | What it is | Trust |
|---|---|---|
| `docs/reference/PIL-HANDOVER.md` | The most recent cross-repo handover (2026-09-14, split into state/plan the same day): what's built in `merp-console`, what PIL actually is, the three unresolved conflicts. State only — no plan content lives here anymore. Written *after* the inventory below, summarizing it for a fresh session. | **High** — a summary, cross-check against the inventory for detail. |
| `docs/reference/PIL-PLAN.md` | Phases, ownership, exit criteria, the two data-handling/reachability preconditions on the fixture corpus, and every open `[NEEDS-DECISION]` flag. Owned by Hiba Hasan — everyone else proposes edits. | **High** — the one place sequencing and ownership are decided; don't infer either from the handover. |
| `docs/reference/pil-inventory.md` | What PIL actually is, read from `merp-console`'s side: every file in `contracts`/`adapters` read in full, all 9 ADRs read, the suite actually installed and run. Pre-dates this file's current content in one respect — see §7 for what's since changed. | **High** — verified by running the suite, not by reading `docs/`. |
| `docs/reference/axo-inventory.md` | What `idiaz-io/Axo` actually implements per integration, read from its code — the companion catalogue to the inventory above, deliberately not merged with it. Confirms which AXO capabilities exist, which are demo-gated, and that every AXO credential path is global (`platform_settings`, no `tenant_id`) — the thing PIL's `(tool, tenant, product)` keying exists to prevent. | **High** — read from source. |
| `docs/reference/MERP — System Architecture.pdf` | The architecture diagram: PIL's six components, the API Gateway drawn outside PIL, the store boundary, the "products never call each other" argument, and the still-unspecified capability catalogue. | **Authoritative** for what PIL is *supposed* to be — cross-check against what actually exists; the two disagree in named, disclosed ways (§4). |
| `docs/invariants.md` | Canonical invariant list. `CLAUDE.md` (this file) carries the same content; if they disagree, this file wins. | **Highest**, for the invariants specifically. |
| `docs/phase-a-scope.md` | The original Phase A brief: move the adapter framework out of AXO, translate-only, nothing else. Section 7's ten questions were answered by reading AXO — those answers are ADR-0005 and `docs/reconciliation.md`, not restated here. | **High** for scope; **superseded** for anything the reconciliation later corrected (two corrections are recorded there explicitly). |
| `docs/reconciliation.md` (IDI-195) | The most rigorous document in the repo. Audits six decisions (D1–D6) against the code as it stood, then records exactly what changed to close each. Preserves the original "before" audit unedited specifically so it stays evidence. Read the **Outcome** table first, the audit below it only for the reasoning. | **Highest** for what actually happened and why — every claim is a file, line and command someone else can run, and most are marked `[ran]`. |
| `docs/known-differences.md` | The one intentional AXO/PIL difference (tenant resolution, ADR-0004) and six preserved defects (tenant read from payload in eleven sites total, non-deterministic timestamps) that PIL reproduces on purpose because I-10 forbids fixing them mid-migration. | **High** — each is a file and line. Ticket numbers are still `_to file_` as of the last read; don't assume they've been filed without checking. |
| `docs/adr/0001`–`0010` | One decision each, all `Accepted`. 0001 naming, 0002 version rule, 0003 envelope (amended by 0009), 0004 tenant resolution, 0005 translate-only scope, 0006 versioning split, 0007 fixture capture, 0008 connection config (amends 0005), 0009 sink (amends 0003, closes D4), 0010 repo topology (records why PIL is standalone; does not resolve `merp-console`'s own ADR-05). | **Highest** for the decisions they cover — read the amending ADR, not just the one it amends, or you'll act on a superseded decision. |
| `fixtures/README.md` + `fixtures/` | The parity corpus. **Empty.** Capture requires `PIL_CAPTURE_ENABLED` + `PIL_CAPTURE_SALT` in AXO plus real production traffic — none of which is this repo's to provide. `make parity` fails honestly on an empty corpus rather than passing vacuously. | Accurate description of a real gap, not a stale doc — confirmed live (`ls fixtures/` is empty). |
| `.github/workflows/ci.yml` | Three jobs: `check` (lint+typecheck+test), `fresh-clone` (DoD 8 — README alone), `parity` (requires `AXO_READ_TOKEN` + a pinned `AXO_PARITY_SHA`, **fails** rather than skipping if either is missing). | Matches what's described in `reconciliation.md` — the "green when skipped" false pass pil-inventory.md found has been fixed; confirm this hasn't regressed before citing it. |

---

## 4. Where the architecture disagrees with what's actually here

Three conflicts nobody has resolved, named plainly rather than smoothed over:

1. **Credential scoping — three incompatible models, across three repos.** AXO resolves
   every credential from a global `platform_settings` table with **no `tenant_id` column at
   all** — one Fleet token for the whole deployment, confirmed across seven integrations by
   reading the resolution code directly (`axo-inventory.md`). PIL's `ConnectionProvider` is
   keyed **`(tool, tenant_id, product)`** specifically to prevent one product inheriting
   another's access — QUILL must never hold AXO's write credential for the same tool
   (ADR-0008). `merp-console`'s own schema is keyed **tenant only**, no product dimension.
   All three disagree, and PIL's is the only one of the three actually designed to prevent the
   failure mode the others allow. **This needs a human decision, not code** — it's cheap to
   leave open only because no tenant today holds more than one product's real credentials.
2. **The gateway.** The architecture diagram requires one — "one door for surfaces,"
   authentication/authorization/tenancy/rate-limiting/audit all enforced there. PIL's own
   invariant (I-1) says such a thing cannot live in PIL. Nobody has written down where it does
   live. `merp-console`'s own `CLAUDE.md` (a different repo, different governing document)
   refers to "pil/gateway" as something the console talks to — **no such thing exists in this
   repo, and this repo's own design says building one here is almost certainly wrong.** Most
   likely reading: the gateway is a product's job (something that imports PIL and exposes its
   own API), not PIL's — but that's a reading, not a ratified decision. Until it's written
   down, there is nothing at any URL for a console or product to call "PIL."
3. **The capability catalogue.** The architecture flags this as unspecified and says it
   belongs in PIL ("STILL UNSPECIFIED — how does AXO know which of QUILL's findings it can act
   on? ... Belongs in PIL"). It was **cut outright** by ADR-0009 (IDI-195 D4), on the grounds
   that it had zero consumers at the time. `merp-console` has since built its own — ten
   capability strings with read/write risk levels, product requirements, an adapter→capability
   mapping, all live in its own Postgres, entirely console-authored with no PIL source. The
   handover calls this "a gift, not a gap" and names moving it into PIL as the single
   highest-value, lowest-risk thing available. Nothing has moved yet.

Two more, smaller but real:

4. **This file used to list five components ("Five components, no more"), not six.** The
   architecture draws six; PIL's own prior `CLAUDE.md` silently dropped Bus+orchestrator from
   the count entirely rather than listing it as cut-with-a-reason. That's corrected here (§1)
   — the distinction between "cut" and "never listed" matters, per D4's own reasoning about
   why docs, not just code, had to change.
5. **`max_classification` (CUI/ITAR tenant classification) has no PIL counterpart at all.**
   `merp-console` gates capability providers by a tenant's classification; PIL's only
   `Classification` enum (`redaction.py`) is about *payload field* sensitivity
   (public/internal/confidential/secret) — same name, different axis, easy to confuse. Phase
   A hasn't reached a surface where this would matter yet, so it isn't a bug, just a gap
   nobody's hit.

---

## 5. Credential keying — `(tool, tenant, product)`, and why not `(tool, tenant)`

The obvious shape is one credential per tool: Fleet has an API key, the key goes on the Fleet
connection. **That shape cannot express what MERP actually needs**, and ADR-0008 states the
failure mode precisely: QUILL reads compliance evidence and must never change anything; AXO
remediates and needs write access. With one credential per tool, QUILL holds AXO's credential
— and the failure is silent. Nothing errors, no test goes red; QUILL is simply *able* to do
things it should never be able to do, and the first evidence is an audit finding or an
incident.

So `ConnectionProvider.connection_for(tool, tenant_id, product)` takes all three, none
optional, none defaulted — `product` in particular, because making it optional immediately
produces the one-credential-per-tool lookup this design rules out. `CredentialHandle` carries
`access: read_only | read_write` on the handle itself, so "QUILL must never write" is
checkable in code before acting, not discovered from a 403 afterward.

**What's real today: the shape. What's not: the store, or resolution.** `FileConnectionProvider`
(JSON, read once at construction) and `StaticConnectionProvider` (in-memory, for tests) both
exist. The real tenant-configuration store — a fourth store alongside graph, ledger and
runbook vault — does not, and gets built when a second product actually needs a tool
connection (ADR-0008 was explicit: this is the cheap moment, before any real credential
exists in production). Nothing anywhere resolves a `CredentialHandle` to an actual secret
value — a test asserts no `resolve_secret`-shaped function exists in the module at all. That
arrives with the connect surface, deferred by ADR-0005, and gets its own ADR when it does.

---

## 6. What `merp-console` consumes from here, and how the pin works

`merp-console` never imports this repo and never calls it as a service (I-1, I-4) — it
*extracts static data* from a pinned commit, on purpose, per its own
`docs/reference/pil-sourcing-proposal.md`. The mechanism, from PIL's side:

- **Pinned by commit SHA**, recorded in the console's `docs/reference/pil-pin.txt` —
  currently `5530434`. Bumping the pin is a deliberate, reviewed act: update the hash, run the
  console's `scripts/pil-sync/sync.sh` (clones this repo fresh at that commit, `uv sync`s it,
  extracts, regenerates), review the diff like any dependency bump, commit.
- **What actually gets extracted** — five small, stable shapes, via real Python imports against
  a real install, never parsed out of source text:
  - `SecretStore`, `Access` (`pil_adapters.connection`) → `PilSecretStore`, `PilAccess`
  - `TenantSource` (`pil_contracts.tenancy`) → `PilTenantSource`
  - `MessageKind` (`pil_contracts.envelope`) → `PilMessageKind`
  - `Classification` (`pil_contracts.redaction`) → `PilFieldClassification` — named to avoid
    exactly the confusion §4 point 5 describes; the console's own generated file's docstring
    says so.
  - `CURRENT_SCHEMA_VERSION` (`pil_contracts.versioning`)
  - `TRANSLATOR_TYPES` (`pil_adapters.registry`) → mirrored into a `pil_translators` table
    (key, adapter_version, pil_commit) — **read by nothing in the console app**; it exists
    for comparison against the console's own hand-seeded adapter catalogue, not consumption.
- **What does NOT get extracted, and won't:** the capability-string vocabulary
  (`host.read`, `script.execute`, etc.) and the adapter config-field schemas
  (`ADAPTER_CONFIG_FIELDS`). Both are permanently console-authored, because PIL has no data for
  either — the capability catalogue was cut (§4 point 3), and `ToolConnection.options` is
  deliberately untyped (§5) specifically so this module never has to know about individual
  vendors. If the capability catalogue does move into PIL per the handover's recommendation,
  this is the one part of §6 that would then need rewriting — not before.
- **A change to any of the five modules above is a breaking change for that sync pipeline**,
  even though nothing here has a formal version contract with `merp-console`. Renaming a
  member, changing a shape, or removing a value the console's generator depends on will surface
  as its own CI drift check failing, not as an import error — because the console never imports
  this repo's code at runtime, only at generation time. Worth knowing before renaming casually.

---

## 7. Conventions

- **Plan before writing.** Plan mode, present, get it approved, then build — every task, not
  just the ones on the "ask first" list below.
- **Small commits, one idea each.** A commit that moves code and improves it is two commits
  pretending to be one (this is I-10 applied to git hygiene, not just to output bytes).
- **Every claim in a PR description must be checkable.** "Parity verified" means a command
  someone else can run and see pass — not a sentence someone can be talked out of.
- **Package names are `pil_contracts`/`pil_adapters`, never `pil.contracts`/`pil.adapters`.**
  `PIL` is Pillow's own top-level import name, and macOS's case-insensitive filesystem makes
  `site-packages/PIL/` and `site-packages/pil/` the same directory — the failure mode is
  import shadowing that appears only once some product happens to pull Pillow in, long after
  the naming is load-bearing everywhere (ADR-0001). This is also why the local checkout here
  is `~/pil`, lowercase, not `~/PIL`.
- **Ask rather than assume**, specifically for: anything that would add an HTTP endpoint, a
  server, or a long-running process; a new node/edge/action-class/kind; an unclear tenant;
  PIL importing a product; AXO's current behaviour being ambiguous enough to tempt a guess.
- **`contracts` has zero dependencies, on anything** — not on `adapters`, not on anything
  outside the Python standard library. Enforced by a test reading its own `pyproject.toml`.
  Adding one is an ADR (ADR-0006): a third-party serialiser's next release could change the
  bytes I-9 requires stay stable forever.
- **Do not start components 3–6** (graph, gate, ledger, bus) without a session explicitly
  scoped to one of them, and don't refactor AXO beyond whatever the current phase's wiring
  switch requires.

## Current phase

See `docs/phase-a-scope.md` for the original brief and `docs/reconciliation.md` for what's
actually landed since. In short: the adapter framework exists in PIL, six translators are
ported and tested, the credential-provider interface exists (D2/D3, ADR-0008), the bus is cut
and replaced with a sink (D4, ADR-0009), and AXO's own three-position wiring switch
(`legacy`/`shadow`/`pil`) is real and covers both the webhook and scheduled-poller paths. What
remains, tracked separately (IDI-196): the parity corpus (`fixtures/` is empty — needs
production capture), and the four closing tests (parity passing in CI, shadow-mode zero
differences, a break-it test, a live rollback demonstration) — all four need a running AXO
deployment this repo does not have.

Do not treat "Phase A" as closed. IDI-195's own definition of done lists two items
(parity passing in CI, all four closing tests run) as **not yet satisfiable** from this repo
alone.
