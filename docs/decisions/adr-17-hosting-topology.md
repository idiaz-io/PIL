# ADR-17 options memo — sovereign/air-gap hosting: a decided direction, not examined against what's shipped

**Status: Awaiting decision.** Written by Hiba, 2026-09-23, after reading PIL, `merp-console`,
and AXO directly rather than reasoning from first principles. This is not an ADR — it's the
memo that has to exist before ADR-17 can be written at all, the same role
`docs/decisions/credential-scoping.md` played before ADR-0008 was reconciled.

## The question, reframed

Every reference to ADR-17 across all three repos treats it as an open two-way choice —
"sovereign/air-gap vs. AWS." Reading the actual code changes that framing. **This was
already decided.** `merp-console`'s own I-13 states a direction plainly:

> "No hard cloud dependencies in core. Self-hosted k3s (Proxmox/homelab, airgap-capable) is
> the primary deployment target. AWS (EKS/Aurora/ElastiCache per the AXO spec's Phase 2) is
> an optional commercial profile behind interfaces — nothing in core code may require a
> managed cloud service to function."
> — `docs/reference/MERP-Agent-Handover.md:50`

That is not ambiguous. Sovereign-first is the primary target; AWS is an optional profile
*behind interfaces*, explicitly scoped to "Phase 2." ADR-17 is not "which do we pick" — it's
"has anyone checked whether what's actually running still matches this."

**It doesn't.** This memo's job is to say so plainly, show exactly where, and put the
questions that determine what happens next in front of whoever has standing to answer them
— not to relitigate a direction that's already on the record, and not to guess at business
questions no repo can answer.

---

## 1. What's already decided, and where

Three real, findable decisions, at three different levels of the stack, all pointing the
same direction:

**I-13 (`merp-console`)** — quoted in full above. The standing architectural constraint:
core must run with no hard cloud dependency; a managed-cloud profile is additive, deferred,
and interface-gated.

**A linked, unnumbered ground-truth item** — `merp-console/CLAUDE.md:46`: *"Local-LLM first
for CUI/ITAR data."* The handover connects it explicitly to I-13 (`MERP-Agent-Handover.md:144`),
listing a still-open "CUI/ITAR/air-gap data-handling policy" that would "strengthen I-9/I-13,
[and] include LLM data-isolation rules." Not a separate question — the same decision, applied
to model inference specifically.

**ADR-01 (`merp-console`)** — the graph store's own version of this call, already made for
one component:

> "Graph store: Neo4j — the ITKG is both knowledge graph and CMDB of record. Guidance:
> property-based tenancy + query-library enforcement in shared graphs; per-tenant/per-enclave
> instances for IL/airgap deployments; all core queries openCypher-portable... DECIDED"
> — `docs/reference/MERP-Agent-Handover.md:442`

This is a real precedent, not just a principle: shared instance with property-scoped tenancy
by default, and a named, decided fallback — separate instances per tenant or per enclave —
for exactly the deployment class ADR-17 is about. Nothing about this needs to be invented;
it needs to be generalized, or explicitly declined to be.

**`healing-graph-core`'s Neptune rejection (AXO)** — the one place in any of the three repos
where I-13 was actually followed, with the alternative named and rejected in writing:

> "Amazon Neptune | Requires AWS — violates the air-gapped deployment constraint. No local
> Docker image."
> — `healing-graph-core/DECISIONS.md:36`

This isn't aspirational. `healing-graph-core` has a documented air-gap deployment mode
(`ARCHITECTURE.md:592`, `SECURITY_THREAT_MODEL.md:393` "Air-Gap Mode"), a `LocalFSBackend`
built specifically to make "no network calls whatsoever" true (`SYSTEM_DESIGN.md:74-89`), and
a customer-facing security guide with dedicated Air-Gap Deployment and Data Sovereignty
sections. One component of MERP has already paid the cost I-13 asks for and shipped it.

---

## 2. Where the code contradicts it

Everything below was built after I-13 and ADR-01 existed, and none of it was checked against
either. This is stated as fact, not inference: every doc in all three repos was searched for
any reference connecting these choices back to I-13, ADR-17, or sovereignty — none exists.

**`merp-console`'s Supabase dependency is the console's entire data layer** — Postgres (24
migrations), Auth, and five Edge Functions — not one service among several. It is the actual
hosted supabase.com platform, not the self-hostable OSS project: `supabase/.temp/linked-project.json`
carries a live project ref linked to supabase.com, and no `supabase/config.toml` for a
self-hosted stack exists anywhere in the repo. I-13 says "nothing in core code may require a
managed cloud service to function." Supabase is a managed cloud service the console's core
cannot function without. The one place this gets close to being named is
`apps/console/src/api/client.ts:14-16`, which documents the *client* as hosting-neutral
("nothing here names a cloud, a region or a managed service") — but that neutrality is one
file's API surface, not the data layer sitting underneath it.

**AXO's Vault client reads deployment-specific values from its own process environment at
import time** — `backend/services/vault.py:14-15`: `VAULT_ADDR = os.getenv("VAULT_ADDR",
"http://vault:8200")`, `VAULT_TOKEN = os.getenv("VAULT_TOKEN", "dev-only-token")`, evaluated
once at module load, defaulting to a Docker-Compose hostname. This is the exact anti-pattern
PIL's own ADR-0015 already named when explaining why PIL itself refuses to resolve secrets:
*"process-global, not tenant-configurable... nothing resolves the `vault_addr`/`vault_token`
values a tenant might type into the Integrations screen's form"* (`docs/reference/axo-inventory.md`,
cited in ADR-0015). PIL declined to build this. AXO already has it.

**AXO is deployed on Render**, with live URLs wired directly into environment defaults
(`render.yaml`, e.g. `fleet-u5x3.onrender.com`, `axo-preview-graph.onrender.com`) — a managed
PaaS, not self-hosted infrastructure, for the same backend Vault's env-var pattern already
assumes a specific runtime for.

**AXO's Tier-2 reasoning defaults to a hosted LLM that isn't even the vendor it appears to
be.** The default endpoint is `https://ollama.com/v1` — Ollama's own *hosted cloud API*,
not a self-hosted local model. `merp-console`'s own decisions doc says this plainly:
*"Ollama, as AXO actually ships it, is also a hosted call to a different vendor, not a local
one"* (`docs/erd/DECISIONS.md:123-130`). Something named for local inference is, as shipped,
a second hosted dependency.

**An AWS region is hardcoded into AXO's example configuration** —
`msp-platform/.env.example:8`: `postgresql://...@aws-0-us-west-2.pooler.supabase.com:6543/postgres`.
The primary database backend's own example config pins a specific AWS region, before a
deployer has made any hosting decision at all.

None of these five were built as a deliberate, documented exception to I-13. They were built
because Supabase, Render, and a hosted "local" LLM endpoint are each the fastest way to ship
a working product — a reasonable engineering choice in isolation, made repeatedly, by
different people, at different times, with nobody checking it against the one document that
already answers the question.

---

## 3. What each contradiction costs to fix, and what's already paid

| Component | Cost to align with I-13 | Status |
|---|---|---|
| `healing-graph-core` (AXO) | — | **Already paid.** Air-gap mode, `LocalFSBackend`, Memgraph over Neptune, a real customer-facing security guide. Proof this is achievable, not just aspirational — cite it, don't re-derive it. |
| AXO `msp-platform` — Vault | Parameterize `VAULT_ADDR`/`VAULT_TOKEN` per deployment instead of reading process env at import; needs the same kind of interface PIL's own `ConnectionProvider` already models, applied to secret-store location itself | Not started |
| AXO `msp-platform` — hosting | Render exit, or a documented, deliberate decision to keep Render for the commercial profile only and build a separate self-hosted deploy path for the sovereign one | Not started |
| AXO — local LLM | An actual local-inference provider does not exist in any repo today. This is not a swap; it's new work — model hosting, GPU/CPU capacity planning, a real interface behind which Anthropic/hosted-Ollama and a local model are interchangeable | Not started, and not even scoped |
| `merp-console` — Supabase | The largest lift of the five: migrating the console's entire data layer (Postgres + Auth + Edge Functions) off a hosted platform, or building and maintaining a parallel self-hosted-Postgres-plus-auth path for a sovereign tier | Not started; no migration path documented anywhere |

**The CUI/ITAR LLM gap is worth stating on its own, because it is not solved by picking
either path.** No code in any of the three repos today has a local-inference provider that
would satisfy a CUI/ITAR tenant's `llm.infer` requirement. `merp-console`'s own capability
catalogue already encodes the gap correctly rather than hiding it — Anthropic is seeded
`max_classification: standard`, which correctly *blocks* it from serving a classified
tenant (`docs/erd/DECISIONS.md`, migration `0008_seeds.sql:131,162,167`) — but blocking the
wrong answer isn't the same as having a right one. Recommitting to I-13 does not by itself
close this; it only makes closing it required rather than optional. Amending I-13 does not
make it go away either — a defense/CUI customer's requirement doesn't change because an
internal architecture doc did.

---

## 4. Questions only a human can answer

None of the following are in any repo, and no amount of further reading will put them there:

- **Which compliance regime, specifically.** "Sovereign" and "air-gap" aren't one
  requirement — FedRAMP, DoD IL4/IL5, CMMC, and ITAR registration each imply different
  technical floors, different audit burdens, and different timelines. The memo can't pick
  one; whoever signs it needs to have already picked, or needs to say the answer is "not yet
  known."
- **Whether defense/government customers requiring this are a near-term target or a
  hypothetical.** This determines whether the cost in §3 gets scheduled or shelved.
- **Infra and engineering budget for the self-hosted path.** A local-LLM host in particular
  is not a configuration change — it is capacity planning, likely GPU spend, and ongoing
  model-ops work that a managed API trades away. Someone with budget authority has to weigh
  that trade, not this memo.
- **Whether Supabase is a deliberate, accepted exception for a commercial-only tier, or
  unpaid technical debt against I-13.** The code doesn't distinguish these — no doc frames
  it as an approved exception, but no doc flags it as debt either. It has simply never been
  examined. That has to be decided, not discovered.
- **Timing.** I-13 itself calls AWS "Phase 2" of the AXO spec. Nothing in any of the three
  repos says whether that phasing still holds, has already been superseded by what shipped,
  or was never really sequenced in the first place.

---

## 5. Two paths out

**A. Recommit to I-13.** Treat the standing decision as still correct, and scope the rework
in §3 as tracked, prioritized work rather than an accumulating gap nobody owns: a
parameterized secret-store location for AXO, a Render exit or a genuinely separate
sovereign deploy path, a real local-LLM provider, and a decision on Supabase — migrate, or
build a parallel sovereign-tier data layer. This path costs the most up front and pays down
debt that's already been accruing silently.

**B. Amend I-13.** Write the ADR that says, plainly, what has actually happened: the
commercial/hosted path is the de facto primary target today, sovereign/air-gap is the
exception that gets built when a real customer requires it, and the CUI/ITAR LLM gap is
explicitly out of scope until that customer exists. This costs little today and is honest
about present reality, at the cost of walking back a documented commitment and accepting
that "primary target" and "what's shipped" have already diverged without anyone deciding
that was acceptable.

**This memo does not recommend between them.** Both are real, coherent positions; the
choice between them is exactly the kind of business call — compliance target, customer
pipeline, budget — that §4 lists and that no repo can answer. What this memo does say is
that the current state — I-13 on the books, unexamined contradictions shipping anyway — is
not a third option. It is path B without the ADR that would make it honest.
