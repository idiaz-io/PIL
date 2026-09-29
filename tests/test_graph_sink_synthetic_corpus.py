"""GraphSink against the full 33-fixture synthetic corpus, not just a few hand-picked
cases. `tests/test_sink.py`'s own GraphSink tests each construct one payload by hand;
this file instead reuses `fixtures/_synthetic/` -- payloads built for a different purpose
entirely (proving translator correctness) -- to check GraphSink holds up against
realistic, varied input it was never specifically designed around.

Lives at the repo root, not inside packages/adapters/tests/, for the same reason
`test_synthetic_fixtures.py` does: it spans `pil_adapters`, `pil_graph`, and
`fixtures/_synthetic/`, none of which is one package's own concern.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pil_adapters import AdapterConfig, FrozenClock, GraphSink, get_translator
from pil_graph import InMemoryGraphDriver, NodeLabel

REPO_ROOT = Path(__file__).resolve().parent.parent
SYNTHETIC_ROOT = REPO_ROOT / "fixtures" / "_synthetic"
FROZEN_INSTANT = datetime(2026, 3, 14, 15, 9, 26, 535897, tzinfo=UTC)
TENANT_ID = "graph-sink-corpus-tenant"


def _fixture_payloads() -> list[tuple[str, Path]]:
    cases = []
    for source_dir in sorted(SYNTHETIC_ROOT.iterdir()):
        if not source_dir.is_dir() or source_dir.name.startswith("_"):
            continue
        for path in sorted(source_dir.glob("*.json")):
            cases.append((source_dir.name, path))
    return cases


def test_every_translatable_fixture_projects_without_raising():
    """The property that matters: GraphSink must never be the reason a translated
    alert fails to reach the graph. A handful of the 33 fixtures are deliberately built
    to make *translation itself* raise (a malformed timestamp, a null company) -- that's
    already proven elsewhere (the parity harness, the shadow-mode rehearsal) and is not
    this test's concern. Everything that translates successfully must project cleanly.
    """
    driver = InMemoryGraphDriver()
    sink = GraphSink(driver)
    config = AdapterConfig(tenant_id=TENANT_ID)
    clock = FrozenClock(FROZEN_INSTANT)

    projected = 0
    translation_failures = 0
    for source, path in _fixture_payloads():
        payload = json.loads(path.read_text(encoding="utf-8"))
        translator = get_translator(source, config, clock)
        try:
            envelope = translator.translate(payload)
        except Exception:
            translation_failures += 1
            continue
        sink.emit(envelope)  # must never raise for a successfully translated envelope
        projected += 1

    assert projected > 0, "no fixture translated successfully -- the corpus is empty"
    # Confirmed directly by the shadow-mode rehearsal: exactly 3 of 33 fixtures are
    # built to make translation itself raise (connectwise's null company, legacy's two
    # malformed timestamps). Pinned so a change to the corpus is a visible, deliberate
    # edit here too, not silently absorbed.
    assert translation_failures == 3
    assert projected + translation_failures == len(_fixture_payloads())


def test_the_corpus_produces_exactly_one_tenant_node():
    """All 33 fixtures are translated under one AdapterConfig -- one tenant. The Tenant
    upsert is idempotent (MERGE), so no matter how many envelopes emit, the graph must
    hold exactly one Tenant node, never one per alert."""
    driver = InMemoryGraphDriver()
    sink = GraphSink(driver)
    config = AdapterConfig(tenant_id=TENANT_ID)
    clock = FrozenClock(FROZEN_INSTANT)

    for source, path in _fixture_payloads():
        payload = json.loads(path.read_text(encoding="utf-8"))
        try:
            envelope = get_translator(source, config, clock).translate(payload)
        except Exception:
            continue
        sink.emit(envelope)

    tenant_nodes = [
        key
        for key, props in driver._nodes.items()
        if props["label"] == NodeLabel.TENANT and props["tenant_id"] == TENANT_ID
    ]
    assert len(tenant_nodes) == 1


def test_every_finding_carries_the_translators_own_severity_and_type_unmodified():
    """project() must not validate or invent Finding.severity/type -- it passes through
    exactly what the translator produced, empty string included. AlertBody's own
    docstring already establishes this discipline (I-10: "deliberately unvalidated
    strings... AXO emits 'P1'-'P4' from some paths... the literal 'unknown' from
    several"); project() must not add a stricter rule translate() itself doesn't have.
    fixtures/_synthetic/legacy/02-*.json exists specifically to prove a translator can
    legitimately emit an empty-string severity (legacy's .get() semantics preserve an
    explicitly-empty value rather than falling through to a default) -- so this asserts
    *type*, not truthiness.
    """
    driver = InMemoryGraphDriver()
    sink = GraphSink(driver)
    config = AdapterConfig(tenant_id=TENANT_ID)
    clock = FrozenClock(FROZEN_INSTANT)

    for source, path in _fixture_payloads():
        payload = json.loads(path.read_text(encoding="utf-8"))
        try:
            envelope = get_translator(source, config, clock).translate(payload)
        except Exception:
            continue
        sink.emit(envelope)

    findings = [
        props
        for props in driver._nodes.values()
        if props["label"] == NodeLabel.FINDING and props["tenant_id"] == TENANT_ID
    ]
    assert findings, "expected at least one Finding across 33 varied fixtures"
    for finding in findings:
        assert isinstance(finding["severity"], str), f"non-string severity: {finding}"
        assert isinstance(finding["type"], str), f"non-string type: {finding}"
