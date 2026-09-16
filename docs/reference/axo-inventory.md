# AXO integration inventory — where AXO and PIL disagree

Companion to `docs/reference/pil-inventory.md`, not a merge of it. **Two source-of-truth
catalogues exist now, and they don't agree.** PIL's `pil_translators` is narrow, tested,
and migrated — six sources, alert-translation only. AXO's own integrations screen is
broader — ten tools, a real config UI for every one of them — and was never migrated
through PIL's rigor at all. Stating that plainly, rather than merging the two into one
list, is the point of this document existing separately.

**Source:** `https://github.com/idiaz-io/Axo`, cloned read-only to `/tmp/Axo` (not
vendored — CLAUDE.md's "do not touch `~/Axo`" is about the local checkout at that path;
this is a separate, disposable clone elsewhere).

**Branch note.** The requested branch, `merp-itkg-spine`, does not exist — it was merged
into `merp-integration` via PR #47 (`merp-integration`'s tip commit is literally *"Merge
pull request #47 from idiaz-io/merp-itkg-spine"*) and deleted afterward, standard
post-merge cleanup. `merp-integration` is where that content lives now; that's what was
read. Commit `b04cae7`, 2026-08-15.

**Method.** Every claim below is a file this repo's clone still has, read in full or
grepped precisely — not inferred from the integrations screen's copy text alone, though
that screen's own source (`msp-platform/desktop-v2/src/data/integrations.js`) is itself
one of the files read, and is more detailed than anything PIL captured (real field
lists, types, hints — not just a catalogue key).

---

## Two things true of every integration below, not repeated ten times

**AXO has no capability-string vocabulary anywhere in its code.** Grepped the whole
backend for `host.read`, `script.execute`, `alert.subscribe`, `repo.read`, `repo.write`,
`llm.infer`, `policy.enforce`, `ticket.create`, `notify.send` — zero real hits. This
vocabulary is a merp-console/PIL invention with no AXO source either, exactly as
CLAUDE.md already records for the vocabulary's origin generally. Every "capability" named
below is *inferred* from what the integration's code actually does (reads hosts? executes
scripts? opens tickets?), never read from an explicit AXO-side list.

**Every credential path in AXO is global, not tenant-scoped.** Fleet, GitLab, ConnectWise,
SL1/ScienceLogic, Vault, Anthropic, Slack — all of them resolve configuration through the
same pattern: a `platform_settings` DB table with **no `tenant_id` column at all** (a
single row per setting key, for the whole deployment), falling back to environment
variables. This is a structural mismatch with both PIL's `ConnectionProvider` (keyed
`tool, tenant_id, product`, specifically to stop one tenant's credential leaking to
another) and this console's own tenant-scoped `connections`/`credential_refs`. It is
bigger than any single integration: **AXO today cannot express "tenant A's Fleet token"
as distinct from "tenant B's Fleet token"** — there is one Fleet token, process-wide. This
is not new information (the access-model doc already flagged Axo's schema as having zero
foreign keys), but it is now confirmed at the credential layer specifically, for every
integration, by reading the actual resolution code rather than the schema.

---

## The four gaps, read in full

### Ollama — the "self-hosted local LLM" is not, by default, self-hosted or local

**Config (`integrations.js`):** none, on purpose — the card is `readOnly: true` with the
note *"Ollama is configured on the AI Model page since it shares the model selector."*
The Integrations screen's Ollama card is a pointer, not a form.

**Backend (`backend/services/reasoning/tier2_ollama.py`, `backend/config.py`):** real —
an actual HTTP call to an OpenAI-compatible `/chat/completions` endpoint, with retry-once
on 500, response parsing, and generated-script validation before use. This is genuinely
working code, not a stub.

**The finding that matters:** the endpoint it calls is controlled by
`lambda_api_url`/`lambda_model`/`lambda_api_key` settings (`backend/config.py:48-50`),
and their **defaults** are:

```python
lambda_api_url: str = os.getenv("LAMBDA_API_URL", os.getenv("OLLAMA_API_URL", "https://ollama.com/v1"))
lambda_model: str  = os.getenv("LAMBDA_MODEL",   os.getenv("OLLAMA_MODEL",   "gemma4:31b"))
```

`https://ollama.com/v1` is Ollama's own **hosted cloud API**, not a self-hosted local
instance. The variable is named `lambda_*` first — a nod to Lambda Cloud, a hosted GPU
provider — with `OLLAMA_*` as a same-shaped fallback; the retry comment even says
*"Lambda Cloud transient failures."* An operator **can** point this at a genuinely local
Ollama server (`http://localhost:11434/v1`), and the code would work identically — but
that is a deployment choice nobody has made by default. **As shipped, "Tier 2" calls a
hosted third-party API, exactly the thing CLAUDE.md's local-LLM-first ground truth (§1.5)
and this project's own open question #7 (`llm.infer`'s only provider being hosted,
unusable for a `cui`/`itar` tenant) already worried about — Ollama does not resolve that
open question by existing.** It's a second hosted API, not a local one, until someone
changes the config.

Also worth noting: `triage_model` defaults to `"claude"`, not `"gemma"` — meaning Tier 3
(Claude review) is invoked by default; `should_invoke_tier3` only returns unconditionally
`False` in `gemma`-only mode, which is not the shipped default either.

**Capabilities (inferred):** `llm.infer`. **No classification restriction is enforced in
code** — nothing here checks a tenant's classification before calling out, hosted or not.

**PIL disagreement:** PIL has no Ollama translator at all — it isn't a translation source,
it's a reasoning-tier LLM call, outside what Phase A's adapter framework covers.

---

### GitLab — real, and the actual provider for the orphaned `repo.read`/`repo.write`

**Config (`integrations.js`):** `gitlab_url`, `gitlab_project_id`, `gitlab_token`
(password field), `gitlab_sync_interval`.

**Backend (`backend/services/gitlab_service.py`, 286 lines, read in full):** real and
substantial. An async httpx client against GitLab's actual `v4` API:
`create_branch`, `delete_branch`, `create_commit` (multi-file actions), `create_merge_request`,
`merge_merge_request`, `close_merge_request`, `get_file` (raw content), `get_commit`,
`get_commit_log`, `get_diff`. Config resolves `platform_settings` → env vars
(`GITLAB_URL`/`GITLAB_TOKEN`/`GITLAB_PROJECT_ID`), global as described above.
**`test_connection()` is real too** — it actually calls GitLab and reports success/failure
with the project's name. AXO can genuinely test this connection; merp-console cannot test
any connection at all (no service exists to call — see `pil-inventory.md` §1). That's a
real capability gap in the other direction, worth naming.

**Capabilities (inferred):** both halves of the vocabulary — `repo.read` (`get_file`,
`get_commit`, `get_commit_log`, `get_diff`) and `repo.write` (`create_branch`,
`create_commit`, `create_merge_request`, `merge_merge_request`, `close_merge_request`,
`delete_branch`). This directly closes `DECISIONS.md` #4's other open half: Addigy's
resolution left `repo.read`/`repo.write` still unprovided; GitLab is that provider.

**PIL disagreement:** PIL has no GitLab translator — GitLab isn't an alert source, it's a
GitOps/write surface, entirely outside Phase A's translate-only scope.

---

### Zabbix — a complete config form with no backend behind it at all

**Config (`integrations.js`):** the fullest form of any integration —
`zabbix_url`, `zabbix_api_token`, `zabbix_username`/`zabbix_password` (legacy fallback),
`zabbix_poll_interval`, plus an `enableKey` toggle (`ZABBIX_SYNC_ENABLED`).

**Backend:** nothing. Grepped `msp-platform/backend/` for `zabbix` (case-insensitive):
**one hit**, and it's a string literal inside a type comment —
`platform: str # "sl1" | "addigy" | "zabbix" | "fleet" | "webhook"`
(`backend/services/reasoning/interfaces.py:28`) — an enumeration of a *possible* value,
never assigned, read, or acted on anywhere. No client, no poller, no route, no test. This
is the one integration on the real screen that is **entirely aspirational** — a
fully-designed UI form with zero lines of code behind it.

**Capabilities:** none real. If built to match its own description ("polls Zabbix
problems via the JSON-RPC API and pulls hosts into the CMDB"), it would be `host.read`/
`host.list`, same shape as Fleet/ScienceLogic's inventory side.

**PIL disagreement:** PIL has no Zabbix translator either — consistent on this one, both
catalogues agree Zabbix isn't real yet, they just disagree on whether it's *presented* as
real. AXO's UI presents it identically to Fleet; nothing distinguishes a fully-wired
integration from this one at a glance.

---

### HashiCorp Vault — infrastructure, not a connectable adapter. Direct answer below.

**Config (`integrations.js`):** `vault_addr`, `vault_token` — present as a normal card,
indistinguishable in the UI from GitLab or Fleet.

**Backend (`backend/services/vault.py`, 104 lines, read in full):** real HTTP calls to a
Vault KV v2 endpoint (`get_secret`, `init_vault`) — but **process-global, not
tenant-configurable, and the UI fields are not wired to it at all.** `VAULT_ADDR` and
`VAULT_TOKEN` are read once from environment variables at import time
(`backend/services/vault.py:14-15`); nothing in this file reads `platform_settings`, and
nothing resolves the `vault_addr`/`vault_token` values a tenant might type into the
Integrations screen's form. Typing into those two fields does not currently change where
this code looks. Vault is also the *fallback target* for other integrations' own secrets
(`_ENV_MAPPING` maps `anthropic/api_key`, `connectwise/api_key`, etc. to env var names) —
it's the thing underneath the other integrations, not a peer to them.

**Direct answer to the question asked:** **Vault should stay infrastructure, not become a
connectable adapter**, and AXO's own code agrees even though AXO's own UI doesn't. Three
reasons, all from what was actually read:

1. It has no tenant dimension anywhere — a single `VAULT_ADDR`/`VAULT_TOKEN` for the whole
   deployment. Modelling it as a per-tenant `connections` row would let the schema express
   something the backend can't act on.
2. It's the resolution mechanism *for* other credentials, not a data source or an action
   surface itself — it has no analogue to `host.read` or `repo.write`; there is nothing to
   grant a product against.
3. `credential_refs.store` already carries `'vault'` as a value (migration 0018, sourced
   from PIL's own `SecretStore` enum) — the concept this console needs from Vault already
   has a home, and it's a property of a credential, not a row in `adapters`.

If a real per-tenant secret-store *connection* concept is ever needed (which Vault
address a tenant's secrets resolve against), that's a new, deliberate design question —
not something "Vault is one of ten cards" answers by default.

---

## The six already seeded, checked against PIL's port

### Fleet — agrees with PIL closely; AXO's real surface is bigger

**Config (`integrations.js`):** `fleet_url`, `fleet_api_key`, `fleet_enroll_secret`, plus
three toggles (`FLEET_SYNC_ENABLED`, `FLEET_SYNC_SOFTWARE`, `fleet_healing_enabled`) —
richer than the two fields (`Fleet URL`, `API token`) this console currently seeds.

**Backend (`backend/integrations/fleet_healing_adapter.py`, 764 lines):** confirmed still
matches PIL's own characterisation exactly — no `demo_mode` anywhere, every method real:
`normalize_alert`, `fetch_device_details`, `check_connectivity`, `execute_on_device`,
`verify_alert_cleared`, `verify_device_state`, `poll_events`. Config resolves
`platform_settings` (`fleet_url`, `fleet_api_key`), global as noted above.

**Capabilities (inferred):** `host.read`, `host.list` (inventory side), `script.execute`
(`execute_on_device` is real, not demo-gated — the one adapter where this is actually
true). Matches this console's existing seed (`fleet` → `host.read`, `host.list`,
`script.execute`) exactly.

**PIL disagreement:** none of substance — PIL ported exactly the one real method
(`normalize_alert`) and documented the rest as demo-gated in AXO, which this read
confirms is still accurate. The three sync toggles AXO's form has, and this console's
`adapter_config_fields` doesn't, are the only concrete gap.

### ScienceLogic / SL1 — three AXO code paths, PIL ported two, both alert-shaped

Confirms and sharpens the inventory doc's earlier finding. AXO has **three**
ScienceLogic-related files, not two:

1. `backend/integrations/sl1_adapter.py` — the healing/alert path. `demo_mode: bool =
   True` by default (`sl1_adapter.py:35`). PIL ported this as `sl1`.
2. `backend/integrations/sciencelogic/normaliser.py` — the webhook alert path (PIL's own
   docs already characterised this as AXO's best-tested normaliser). PIL ported this as
   `sciencelogic`.
3. `backend/services/adapters/sl1_adapter.py` — **a third file PIL never touched**: real
   `fetch_devices()` → `NormalisedDevice`, `test_connection()`, config via
   `platform_settings` → env, no demo flag. This is the **CMDB/inventory** path — the same
   shape as Fleet's inventory side, and the same thing ADR-0005 explicitly deferred
   ("Migrate the inventory path instead... Deferred to Phase B"). It is real, working
   code, sitting outside PIL's migrated scope entirely — not stubbed, just not ported yet.

**Capabilities (inferred):** the two alert paths give `alert.subscribe`; the untouched
inventory path gives `host.read`/`host.list` — which this console's `sciencelogic` seed
row already claims (`host.read`, `host.list`, `alert.subscribe`), correctly anticipating a
capability PIL's own translator catalogue doesn't cover at all.

**PIL disagreement:** PIL's two-translator split (`sciencelogic`, `sl1`) covers only the
alert-shaped half of what AXO's ScienceLogic integration actually does. The inventory
half is real in AXO and absent from PIL. Migration 0020's fix (SL1 is not its own
*connection*) is unaffected by this — it was about the console's presentation, and stands.

### ConnectWise — two separate real surfaces, this console's seed only has one

**Config (`integrations.js`):** `connectwise_api_url`, `connectwise_company_id`,
`connectwise_api_key`, `CONNECTWISE_CMDB_SYNC_ENABLED` toggle.

**Backend — two files, both real, doing different things:**

- `backend/services/adapters/connectwise_adapter.py` (315 lines) — CMDB inventory:
  `fetch_devices()` → `NormalisedDevice`, `test_connection()`, `is_configured()`. No
  demo flag.
- `backend/integrations/connectwise/client.py` — ticketing, a full client:
  `create_ticket`, `update_ticket`, `close_ticket`, `add_ticket_note`,
  `create_time_entry`, plus board/company/member lookups. Also real, also
  `platform_settings` → env, module-level `configure()` rather than a class.

**Capabilities (inferred):** `ticket.create` (this console already seeds this) **plus
`host.read`/`host.list`, which it does not.** The CMDB-sync half of ConnectWise is real in
AXO and currently invisible in this console's catalogue.

**PIL disagreement:** PIL only ported the ticket-normalisation/translate side
(`ticket_normaliser.py`, feeding the healing pipeline) — consistent with `ticket.create`.
It never touched the CMDB-fetch side either, same shape as the ScienceLogic gap above.

### Addigy — matches PIL's characterisation exactly

**Config (`integrations.js`):** `addigy_client_id`, `addigy_client_secret`,
`addigy_tenant_id`, `addigy_api_url`.

**Backend (`backend/integrations/addigy_adapter.py`, 303 lines):** `demo_mode: bool =
True` by default (`addigy_adapter.py:34`), full method set present
(`normalize_alert`, `fetch_device_details`, `check_connectivity`, `execute_on_device`,
`verify_alert_cleared`, `verify_device_state`, `poll_events`) but demo-gated exactly as
PIL's own ADR-0005 already documented. `_client_id`/`_client_secret` are populated from
settings/vault per the constructor comment, but every non-`normalize_alert` method
branches on `self._demo` regardless of whether real credentials are present.

**Capabilities (inferred):** `alert.subscribe`, matching this console's current seed
exactly (migration 0017 seeded only `alert.subscribe` for Addigy, on the same reasoning:
only translation is real). No disagreement to correct here.

### Anthropic (Claude) — real, global, gracefully degrading

**Config (`integrations.js`):** `anthropic_api_key`, `anthropic_model`.

**Backend (`backend/services/reasoning/tier3_claude.py`, 320 lines):** real —
`anthropic.AsyncAnthropic` client, called for both plan-review and full-fallback roles.
Degrades cleanly (`tier_used = "tier3_skipped_no_key"`) rather than erroring when
`ANTHROPIC_API_KEY` is unset, logging the skip once rather than spamming.

**Capabilities (inferred):** `llm.infer`, matching this console's seed. Consistent with
`DECISIONS.md` #7's own framing: Anthropic is a hosted API with no classification
awareness in AXO's code either — the `cui`/`itar` gap this console's seed already flags
(`max_classification = 'standard'` on `anthropic`/`llm.infer`) is real on AXO's side too,
not merp-console being unusually strict.

### Slack — two independent real paths, one of them not even DB-backed

**Config (`integrations.js`):** `slack_webhook_url`, `slack_channel`.

**Backend — two separate, real mechanisms:**

- `backend/services/slack.py` — a bare webhook poster, `SLACK_WEBHOOK_URL` read directly
  from the environment (not `platform_settings` at all), gated on
  `SLACK_ENABLED = bool(SLACK_WEBHOOK_URL)`.
- `backend/services/slack_bot.py` + `slack_notifications.py` — a fuller bot (slash
  commands, formatted notifications), using `settings.slack_bot_token`
  (`backend.config`, also env-sourced). Per-event-type toggles
  (`notify_auto_healed`, `notify_escalation`, etc.) live in `_notification_config`, an
  **in-memory dict** — restarting the process resets which event types notify, since
  nothing persists it.

**Capabilities (inferred):** `notify.send`, matching this console's seed. The in-memory
config detail doesn't change the capability, just the operational reality of how
durable a toggle is.

---

## Summary — who claims what

| Adapter | PIL translator | AXO integrations.js card | AXO backend reality |
|---|---|---|---|
| `fleet` | ✅ `fleet` | ✅ 6 fields | Real, full method set |
| `sciencelogic` | ✅ `sciencelogic` (webhook) | ✅ combined "ScienceLogic SL1" card | Real (webhook) |
| `sl1` | ✅ `sl1` (healing) | — (same card as above) | Demo-gated except translate |
| *(sl1 inventory)* | ❌ not ported | — (same card) | Real, untouched by PIL |
| `connectwise` | ✅ (ticket translate only) | ✅ 4 fields | Real ticketing **and** real CMDB-fetch (2nd untouched by PIL) |
| `addigy` | ✅ | ✅ 4 fields | Demo-gated except translate |
| `legacy` | ✅ | — (no card; AXO has no generic fallback UI) | n/a |
| `anthropic` | — (not a PIL concern) | ✅ 2 fields | Real, degrades gracefully |
| `slack` | — | ✅ 2 fields | Real, two parallel paths |
| `ollama` | ❌ | ✅ read-only pointer card | Real, but defaults to hosted `ollama.com` |
| `gitlab` | ❌ | ✅ 4 fields | Real, full read+write, real connection test |
| `zabbix` | ❌ | ✅ 6 fields | **Nothing.** One string in a type comment. |
| `vault` | — (PIL's `SecretStore` enum has the value, not a translator) | ✅ 2 fields | Real, global, **not wired to those 2 fields at all** |

---

## Not done here

No seeding. No migration. No change to `adapters`, `adapter_config_fields`, or
`adapter_capabilities`. This is inventory only, same discipline as
`pil-inventory.md` — report first, decide separately.
