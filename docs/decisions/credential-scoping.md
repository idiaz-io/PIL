# Credential-scoping decision memo

**Status: Awaiting approval.** Written by Hiba, 2026-09-19. This is not an ADR — it's the
memo `PIL-PLAN.md`'s Monday entry commits to shipping, submitted for whoever has standing to
approve it. **Phase 3 adapter work (Fleet's connect/fetch/execute, ported from AXO) does not
start until this is approved.** If it comes back with named objections rather than silence,
Thursday/Friday become hardening instead, per the plan's own Wednesday checkpoint language —
not started on a guess either way.

## The question

Three places in this codebase model "which credential does a caller get for this tool,"
and they disagree:

1. **AXO** — `platform_settings`, a global key-value table, **no `tenant_id` column at all**.
2. **PIL** — `pil_adapters.connection.ConnectionProvider`, keyed **`(tool, tenant_id,
   product)`**.
3. **merp-console** — `connections`/`credential_refs`, keyed by **`tenant_id` only**; product
   differences are expressed one layer up, in `grants` (`product, connection, capability`),
   never on the credential itself.

Phase 3 adapter work needs one answer, not three. This is that answer, and the reasoning
behind it.

## The three models, read in full, not surveyed

### Model A — AXO: global, no `tenant_id`

**Can express:** one secret per setting key, for the whole deployment. Confirmed across all
ten integrations in `docs/reference/axo-inventory.md` — Fleet, GitLab, ConnectWise,
SL1/ScienceLogic, Vault, Anthropic all resolve `platform_settings` → environment, with no
tenant dimension anywhere in the resolution path. Some UI fields aren't even wired to it:
Vault's `vault_addr`/`vault_token` form fields are cosmetic — the backend reads `VAULT_ADDR`/
`VAULT_TOKEN` from the environment at import time and ignores whatever's typed into the
screen.

**Can't express:** two tenants using the same tool with different credentials — structurally,
not as a missing feature. There is one Fleet token, process-wide.

**What breaks if adopted as the standard:** everything downstream that already assumes tenant
isolation — PIL's own I-5 and merp-console's entire RLS model exist specifically because a
credential-layer tenant leak is the worst class of bug this architecture is built to prevent.
Not a real candidate; read in full because the memo asked for it, not because it's live.

**Cost to migrate the other two onto it:** doesn't apply — strictly less expressive than what
either already needs.

### Model B — PIL's `ConnectionProvider`, keyed `(tool, tenant_id, product)`

**Can express:** the maximal case. Two different real credentials for the same tool, same
tenant, different products — AXO read-write, QUILL read-only, distinct `CredentialHandle`s,
distinct secrets. `(tool, tenant, product)` is a strict superset of `(tool, tenant)`. D3's own
stated reason for this shape: a shared credential means *"QUILL simply becomes able to do
things it should not"* — silently, at the credential layer, regardless of what application
code checks.

**Can't express directly:** merp-console's actual UX. The console's own ground truth is
explicit — *"A connection is made once for the organisation and lent out"* and *"if a thing
would have to be duplicated per product, it belongs to the substrate."* Taken literally,
PIL's shape requires a distinct credential per granted product from day one.

**What breaks if adopted literally everywhere:** the console's Connections screen model — one
admin, one Fleet connection, N products granted capabilities from one secret. Forcing
per-product credentials here is a straight regression for the one thing that's actually live
today.

**Cost to migrate the other two:**
- AXO → this model: the "fourth store" D2 already defers, plus rewiring all ten integrations'
  config-resolution call sites. Large, but it's D2/D3's own already-planned migration, not new
  work invented here.
- merp-console → this model: a `product_key` column on `connections`/`credential_refs`, and
  either real secret duplication per grant or an unused column for the common case — schema
  churn for something nothing in the mocks or ground truth currently asks for.

### Model C — merp-console: tenant-scoped, no product dimension on the credential

**Can express:** per-tenant isolation (the axis RLS actually enforces) plus per-product
*capability* differences on one shared secret, via `grants` as its own triple. A product can
hold `host.read` but not `script.execute` against the same connection without a second
secret. Real and working today.

**Can't express:** two products holding genuinely different *credentials* for the same tool —
not different permission tiers on the same one, an actual second secret. Exactly one
`credential_refs` row per `connection`. Confirmed directly: `product_key` appears nowhere on
`connections`, `credential_refs`, or `connection_config_values` (`0004_connections_and_
adapters.sql`, `0005_products_and_entitlement.sql`) — only on `grants` and `pending_requests`
(`0019_connections_credential_gate_and_ledger_seal.sql`), one layer above the credential.

**What breaks if adopted as the standard everywhere:** D3's stated security property,
directly — see "The weaker property, stated plainly" below.

**Cost to migrate the other two:**
- AXO → this model: cheaper than Model B. Needs *only* a tenant-scoped store, nearly
  identical to merp-console's existing schema. Same ten call-site rewrites, simpler target
  shape.
- PIL → this model: not a migration, a reversal of D3. Would need its own ADR overturning
  D3's stated reasoning, not just a refactor.

## Recommendation

This was never really a three-way choice. It looks like one only because the interface's
shape and the store's default provisioning behaviour were being decided as one question.
Separated, it resolves cleanly:

1. **Keep PIL's `ConnectionProvider` interface exactly as it is** — `(tool, tenant_id,
   product)`. No ADR to reverse D3; nothing here costs anything to keep, since it's an
   interface plus a file-backed test double, not a live store yet.

2. **The real credential store, when built, defaults to one secret per `(tool, tenant_id)`,
   with product-scoping expressed through capability grants — matching merp-console's live
   model — resolved *through* PIL's interface, not around it.** A provider implementation
   returns the *same* `CredentialHandle` for every `product` argument unless a specific
   tenant has configured otherwise. The interface's granularity is a ceiling on what can be
   expressed, not a floor on what must be provisioned — same vocabulary this project already
   uses for `max_classification` ("a ceiling, not a floor").

3. **AXO's migration target is the tenant-scoped store**, with the interface's `product`
   parameter honored but defaulted to shared-per-tenant. This converges AXO and merp-console
   onto the same credential-storage shape, while leaving D3's isolation property a real,
   buildable path for whenever a second product needs it.

4. **merp-console's schema doesn't need a `product_key` column added anywhere right now.**
   Per-product credential isolation, if it's ever needed for a specific tenant, is an
   additive override table joined against `credential_refs` — not a redesign of the base
   tables today.

## The weaker property, stated plainly — not softened

**In the default shared-per-tenant mode, the `product` parameter provides no isolation.**
`connection_for("fleet", "tenant-acme", "axo")` and `connection_for("fleet", "tenant-acme",
"quill")` return the *identical* `CredentialHandle` — same store, same name, same access
level. The only thing stopping QUILL from doing anything AXO's token can do is which
capability was granted to QUILL, checked by application code (the gate), not the credential
itself.

**This is precisely the failure D3 was written to prevent.** D3's own words: *"One shared
login per tool means QUILL can do things it should never be able to do... the failure is
silent."* Under this recommendation's default, that is exactly the situation — silent in the
same way, for the same reason. We are accepting a weaker property than D3 asked for, by
default, in exchange for shipping something now instead of building the full per-product
credential store before any product other than AXO exists to need it. The stronger property
D3 wanted is not abandoned — it's available per-tenant, as an explicit configuration, the
moment someone needs it — but nobody gets it by default, and that is a real, named gap
between what ships and what D3 originally specified, not a detail to gloss over.

## What would trigger revisiting this

**A second product actually requesting different access to the same tool for the same
tenant** — not a hypothetical, a real request: QUILL (or any other product) needing a
distinct credential, not just a distinct capability grant, against a connection AXO already
uses. At that point the default stops being adequate for that tenant, and the per-product
override path this memo's Model B keeps available is what gets exercised — the interface
already supports it; only the store's data needs to grow to include it, for that one tenant,
not a redesign. Until that request exists, building it speculatively is exactly what
`docs/reconciliation.md` and this project's own "report before building" discipline argue
against.
