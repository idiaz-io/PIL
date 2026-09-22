"""Proof against a real Neo4j — not the in-memory fake.

Two independent conditions gate every test here, so the suite stays green with neither:

* the ``neo4j`` driver package installed (``uv sync --group graph-integration`` /
  ``make neo4j-test``) — ``pytest.importorskip`` below skips collection cleanly if not;
* ``NEO4J_TEST_URI`` set to a running instance (``make neo4j-up`` starts one via
  ``docker-compose.neo4j.yml``) — ``NEEDS_NEO4J`` skips each test if not.

Env var names match AXO's own ``itkg_integration_test.go`` exactly (``NEO4J_TEST_URI``,
``NEO4J_TEST_USER``, ``NEO4J_TEST_PASSWORD``, same default password) — point either
language's test suite at the same running container without reconfiguring anything.

``tests/_graph_neo4j_driver.py`` is the thing under test here in the sense that it's the
only new code this file exercises directly; what it's actually *proving* is that
``pil_graph.operations``'/``pil_graph.schema``'s generated Cypher does what their
docstrings claim against a real engine, not just against
:class:`~pil_graph.fakes.InMemoryGraphDriver`'s Python-side reimplementation of the same
semantics.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

neo4j = pytest.importorskip("neo4j", reason="uv sync --group graph-integration, or make neo4j-test")

from pil_graph.operations import CountNodes, UpsertEdge, UpsertNode  # noqa: E402
from pil_graph.vocabulary import EdgeType, NodeLabel  # noqa: E402

# tests/ has no __init__.py (pytest runs with --import-mode=importlib), so
# _graph_neo4j_driver.py is not importable as a relative sibling. Add this directory to
# sys.path and import it by bare name instead -- the same fix test_parity_harness.py
# already applies for scripts/parity.py.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _graph_neo4j_driver import Neo4jGraphDriver  # noqa: E402

NEO4J_TEST_URI = os.environ.get("NEO4J_TEST_URI", "")
NEO4J_TEST_USER = os.environ.get("NEO4J_TEST_USER", "neo4j")
NEO4J_TEST_PASSWORD = os.environ.get("NEO4J_TEST_PASSWORD", "testpassword")

NEEDS_NEO4J = pytest.mark.skipif(
    not NEO4J_TEST_URI,
    reason="NEO4J_TEST_URI not set; no Neo4j instance to test against (make neo4j-up)",
)


@pytest.fixture
def driver():
    """Connect, wipe, apply constraints — same order AXO's own integration test uses."""
    with Neo4jGraphDriver.connect(NEO4J_TEST_URI, NEO4J_TEST_USER, NEO4J_TEST_PASSWORD) as d:
        d.wipe_all()
        d.apply_constraints()
        yield d


# ----------------------------------------------------------------------------------
# Every operation the query builder emits actually executes.
# ----------------------------------------------------------------------------------


@NEEDS_NEO4J
def test_upsert_node_executes_and_is_readable_back(driver) -> None:
    driver.upsert_node(
        UpsertNode(tenant_id="tenant-a", label=NodeLabel.ASSET, id="host-1", props={"os": "linux"})
    )

    assert driver.count_nodes(CountNodes(tenant_id="tenant-a", label=NodeLabel.ASSET)) == 1


@NEEDS_NEO4J
def test_upsert_node_is_a_merge_not_an_insert(driver) -> None:
    """Same tenant, same id, twice -- one node, not two. The whole point of MERGE
    (and of the uid constraint backing it, see GraphDriver's docstring)."""
    for _ in range(2):
        driver.upsert_node(UpsertNode(tenant_id="tenant-a", label=NodeLabel.ASSET, id="host-1"))

    assert driver.count_nodes(CountNodes(tenant_id="tenant-a", label=NodeLabel.ASSET)) == 1


@NEEDS_NEO4J
def test_upsert_edge_executes_between_two_real_nodes(driver) -> None:
    driver.upsert_node(UpsertNode(tenant_id="tenant-a", label=NodeLabel.ASSET, id="host-1"))
    driver.upsert_node(UpsertNode(tenant_id="tenant-a", label=NodeLabel.MISSION, id="mission-1"))

    # Must not raise -- both endpoints exist under this tenant.
    driver.upsert_edge(
        UpsertEdge(
            tenant_id="tenant-a",
            edge_type=EdgeType.RUNS_ON,
            from_label=NodeLabel.ASSET,
            from_id="host-1",
            to_label=NodeLabel.MISSION,
            to_id="mission-1",
        )
    )


@NEEDS_NEO4J
def test_upsert_edge_raises_when_an_endpoint_is_missing(driver) -> None:
    """The one behaviour InMemoryGraphDriver's own tests cannot, by themselves, prove
    (GraphDriver.upsert_edge's docstring): a real MATCH finding no rows must surface as
    LookupError, not as a query that quietly succeeded having done nothing."""
    driver.upsert_node(UpsertNode(tenant_id="tenant-a", label=NodeLabel.ASSET, id="host-1"))
    # mission-1 was never created.

    with pytest.raises(LookupError):
        driver.upsert_edge(
            UpsertEdge(
                tenant_id="tenant-a",
                edge_type=EdgeType.RUNS_ON,
                from_label=NodeLabel.ASSET,
                from_id="host-1",
                to_label=NodeLabel.MISSION,
                to_id="mission-1",
            )
        )


@NEEDS_NEO4J
def test_count_nodes_executes_and_filters_by_label(driver) -> None:
    driver.upsert_node(UpsertNode(tenant_id="tenant-a", label=NodeLabel.ASSET, id="host-1"))
    driver.upsert_node(UpsertNode(tenant_id="tenant-a", label=NodeLabel.MISSION, id="mission-1"))

    assert driver.count_nodes(CountNodes(tenant_id="tenant-a", label=NodeLabel.ASSET)) == 1
    assert driver.count_nodes(CountNodes(tenant_id="tenant-a", label=NodeLabel.MISSION)) == 1


# ----------------------------------------------------------------------------------
# ApplyConstraints: the uid constraint is load-bearing, not setup.
# ----------------------------------------------------------------------------------


@NEEDS_NEO4J
def test_apply_constraints_installs_uid_uniqueness_and_tenant_index(driver) -> None:
    """Direct proof the DDL actually landed, not an inference from behaviour --
    ``SHOW CONSTRAINTS``/``SHOW INDEXES`` is Neo4j's own source of truth."""
    with driver._driver.session() as session:
        constraint_names = {r["name"] for r in session.run("SHOW CONSTRAINTS")}
        index_names = {r["name"] for r in session.run("SHOW INDEXES")}

    for label in NodeLabel:
        name = label.value.lower()
        assert f"{name}_uid" in constraint_names, f"missing uid constraint for {label}"
        assert f"{name}_tenant" in index_names, f"missing tenant index for {label}"


@NEEDS_NEO4J
def test_apply_constraints_is_idempotent(driver) -> None:
    """Re-applying must not raise -- IF NOT EXISTS is the whole point, and a real
    implementation may need to call this on every startup (GraphDriver's docstring)."""
    driver.apply_constraints()
    driver.apply_constraints()


@NEEDS_NEO4J
def test_uid_constraint_prevents_a_duplicate_node_outside_merge(driver) -> None:
    """The failure mode ApplyConstraints exists to prevent, forced directly: a bare
    CREATE (bypassing MERGE, the way a bug or a different code path might) for a uid
    that already exists must be rejected by the database itself, not merely avoided by
    every caller behaving. Without the constraint this would silently succeed."""
    driver.upsert_node(UpsertNode(tenant_id="tenant-a", label=NodeLabel.ASSET, id="host-1"))

    with driver._driver.session() as session, pytest.raises(neo4j.exceptions.ConstraintError):
        session.run(
            "CREATE (n:Asset {uid: $uid, tenant_id: $tenant, id: $id})",
            {"uid": "tenant-a/host-1", "tenant": "tenant-a", "id": "host-1"},
        ).consume()


# ----------------------------------------------------------------------------------
# Cross-tenant isolation against a real database, not just the fake.
# ----------------------------------------------------------------------------------


@NEEDS_NEO4J
def test_cross_tenant_isolation_holds_against_real_neo4j(driver) -> None:
    """Direct port of AXO's own TestGraphCrossTenantLeak (itkg_integration_test.go):
    tenant-a gets 2 assets, tenant-b gets 1, host-1 exists under BOTH tenants -- the
    synthetic uid must keep them distinct rather than collapsing into one node."""
    driver.upsert_node(UpsertNode(tenant_id="tenant-a", label=NodeLabel.ASSET, id="host-1"))
    driver.upsert_node(UpsertNode(tenant_id="tenant-a", label=NodeLabel.ASSET, id="host-2"))
    driver.upsert_node(UpsertNode(tenant_id="tenant-b", label=NodeLabel.ASSET, id="host-1"))

    count_a = driver.count_nodes(CountNodes(tenant_id="tenant-a", label=NodeLabel.ASSET))
    count_b = driver.count_nodes(CountNodes(tenant_id="tenant-b", label=NodeLabel.ASSET))
    count_unknown = driver.count_nodes(
        CountNodes(tenant_id="tenant-unknown", label=NodeLabel.ASSET)
    )

    assert count_a == 2, "tenant-a should see exactly its 2 assets"
    assert count_b == 1, "tenant-b should see exactly its 1 asset -- not tenant-a's 2"
    assert count_unknown == 0, "an unknown tenant must see 0 assets"


@NEEDS_NEO4J
def test_edge_cannot_be_written_across_tenants_against_real_neo4j(driver) -> None:
    """host-1 exists under tenant-a; mission-1 exists only under tenant-b. An edge
    claimed under tenant-a naming mission-1 must not find tenant-b's node -- proving
    the MATCH clause's tenant scoping holds against a real query planner, not just the
    fake's dict lookup."""
    driver.upsert_node(UpsertNode(tenant_id="tenant-a", label=NodeLabel.ASSET, id="host-1"))
    driver.upsert_node(UpsertNode(tenant_id="tenant-b", label=NodeLabel.MISSION, id="mission-1"))

    with pytest.raises(LookupError):
        driver.upsert_edge(
            UpsertEdge(
                tenant_id="tenant-a",
                edge_type=EdgeType.RUNS_ON,
                from_label=NodeLabel.ASSET,
                from_id="host-1",
                to_label=NodeLabel.MISSION,
                to_id="mission-1",
            )
        )
