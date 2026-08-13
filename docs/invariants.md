# The invariants

Canonical copy. `CLAUDE.md` carries the same list so that every session reads it without
being asked; if the two ever disagree, this file is right and `CLAUDE.md` needs patching.

These are not style preferences. Breaking one is a design defect, and several of them
exist because they were violated before and it cost real work.

---

**I-1 · PIL is a library.**
No HTTP surface. No long-running PIL process. Products import it.

**I-2 · One consumer means not shared.**
If exactly one product needs a capability, it belongs to that product, not to PIL. This
is the test that keeps PIL from growing into a second product.

**I-3 · PIL never depends on a product.**
The dependency arrow points one way, always. If PIL needs something from AXO, that thing
belonged in PIL. `import` statements referencing any product are a defect.

**I-4 · Products never call each other.**
AXO does not call QUILL. They cooperate by leaving records where the other will find
them. PIL must never provide a mechanism that makes product-to-product calls easy.

**I-5 · Tenant identity is never taken from input.**
For request-driven work, the tenant comes from a validated token claim. For scheduled
work (pollers), there is no token — so the tenant comes from the **adapter instance's own
configuration**, and an adapter instance may never emit a message for any tenant other
than its configured one. Never read the tenant out of a vendor payload. This is currently
violated in AXO production and is the highest-risk class of bug in the system.

**I-6 · Vocabularies are closed.**
Node types, edge types, action classes and decision outcomes are fixed sets. Extend by
adding properties, never by adding a type. Adding a type is an ADR, not a commit.

**I-7 · Message shapes are versioned from the first line of code.**
Every message carries its schema version. A consumer built for v1 must not crash on a v2
message. Decide the compatibility rule once and encode it in the library.

**I-8 · Secrets are handles, never values.**
Adapter configuration holds a reference to a secret. The value is resolved at the moment
of use and never logged, never stored, never placed in a message.

**I-9 · Deterministic serialisation.**
Anything that will later be hashed or signed must serialise byte-identically every time.
Ordering, whitespace and number formatting all matter. Get this right in contracts now;
retrofitting it invalidates every signature written before the fix.

**I-10 · Behaviour-preserving migration.**
When code moves from a product into PIL, the output must be identical. Not "equivalent" —
identical, proven against saved real payloads. A migration that improves behaviour while
moving it is two changes pretending to be one.

---

## How each one is enforced

An invariant that is only written down is a wish. These are the mechanisms.

| # | Mechanism | Where |
|---|---|---|
| I-1 | Nothing in either package imports a web framework or opens a socket | `tests/test_invariants.py` |
| I-2 | Judgement. No mechanism — this one is a review question. | — |
| I-3 | `ruff` banned-api on every product name, plus an import walk that catches dynamic imports lint cannot see | `pyproject.toml`, `tests/test_invariants.py` |
| I-4 | Follows from I-1 and I-3: PIL offers no transport, so it cannot provide one | — |
| I-5 | `Envelope` rejects an empty tenant; a test asserts every translator emits its configured tenant over every fixture | `packages/contracts/src/pil_contracts/envelope.py`, `tests/test_invariants.py` |
| I-6 | `MessageKind` is an `Enum`; an unknown kind raises rather than being guessed at | `packages/contracts/src/pil_contracts/envelope.py` |
| I-7 | `SchemaVersion.parse` is total; unknown fields are ignored, never rejected | `packages/contracts/tests/test_versioning.py` |
| I-8 | Not yet applicable — Phase A is translate-only and touches no credentials. Arrives with the connect surface, and gets its own ADR. | — |
| I-9 | Canonical JSON, pinned by a golden test that is an ADR to change | `packages/contracts/tests/test_canonical.py` |
| I-10 | The parity harness. Byte-identical or it fails, in CI. | `scripts/parity.py` |

I-2 is the one with no mechanism, deliberately. It is a question to ask in review — "does
more than one product need this?" — and no test can answer it.
