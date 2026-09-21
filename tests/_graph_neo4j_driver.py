"""A real :class:`~pil_graph.driver.GraphDriver`, backed by Neo4j. Dev/test only.

Underscore-prefixed the same way ``scripts/_axo_driver.py`` already is in this repo: this
file breaks I-3/ADR-0011's rule on purpose (it imports a graph-client library) and is not
library code PIL ships. It lives here, not in ``packages/graph``, precisely so it can
break that rule without ``packages/graph`` doing so — enforced by
``tests/test_invariants.py::test_graph_depends_only_on_contracts`` and
``test_graph_imports_only_contracts_and_the_stdlib``, which would fail if this ever moved
into the shipped package.

Requires the ``graph-integration`` dependency group (``uv sync --group graph-integration``
or ``make neo4j-test``) — never installed by a plain ``uv sync``. Importing this module
without it raises ``ModuleNotFoundError``; callers are expected to guard with
``pytest.importorskip("neo4j")`` first, which is what
``test_graph_neo4j_integration.py`` does before ever reaching this import.

Uses the synchronous ``neo4j`` driver, matching :class:`~pil_graph.driver.GraphDriver`'s
own deliberately-sync contract — nothing here needs to colour its caller a coroutine.
"""

from __future__ import annotations

from dataclasses import dataclass

import neo4j

from pil_graph.driver import GraphDriver
from pil_graph.operations import CountNodes, UpsertEdge, UpsertNode
from pil_graph.schema import all_constraint_statements

__all__ = ["Neo4jGraphDriver"]


@dataclass(slots=True)
class Neo4jGraphDriver(GraphDriver):
    """Runs the Cypher :mod:`pil_graph.operations` builds against a real Neo4j.

    Holds one ``neo4j.Driver``; construct with :meth:`connect`, always use as a context
    manager so the underlying connection pool closes.
    """

    _driver: neo4j.Driver

    @classmethod
    def connect(cls, uri: str, user: str, password: str) -> Neo4jGraphDriver:
        """Open a driver and verify connectivity before returning — the same
        fail-fast-on-construction posture ``Connect`` takes in AXO's ``itkg.go``."""
        driver = neo4j.GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
        return cls(_driver=driver)

    def close(self) -> None:
        self._driver.close()

    def __enter__(self) -> Neo4jGraphDriver:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Schema — see GraphDriver's docstring: this is a correctness requirement, not setup.
    # ------------------------------------------------------------------

    def apply_constraints(self) -> None:
        """Install every statement :func:`~pil_graph.schema.all_constraint_statements`
        generates. ``IF NOT EXISTS`` makes each idempotent; DDL runs auto-commit, one
        statement per session run, matching AXO's own ``ApplyConstraints`` exactly (Neo4j
        does not allow schema statements inside an explicit transaction alongside data
        writes)."""
        with self._driver.session() as session:
            for statement in all_constraint_statements():
                session.run(statement)

    def wipe_all(self) -> None:
        """Delete every node and relationship. Test-only, deliberately unscoped — the
        same role AXO's own ``wipeAll`` plays: not part of the tenant-scoped surface,
        useful only against a disposable test database between test runs."""
        with self._driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")

    # ------------------------------------------------------------------
    # GraphDriver
    # ------------------------------------------------------------------

    def upsert_node(self, operation: UpsertNode) -> None:
        cypher, params = operation.to_cypher()

        def _write(tx: neo4j.ManagedTransaction) -> None:
            tx.run(cypher, params)

        with self._driver.session() as session:
            session.execute_write(_write)

    def upsert_edge(self, operation: UpsertEdge) -> None:
        cypher, params = operation.to_cypher()

        def _write(tx: neo4j.ManagedTransaction) -> int:
            result = tx.run(cypher, params)
            record = result.single()
            count: int = record["relationships_written"] if record is not None else 0
            return count

        with self._driver.session() as session:
            written = session.execute_write(_write)

        if written == 0:
            # Cypher's own signal, per GraphDriver.upsert_edge's contract: the MATCH
            # found no endpoint for this tenant, so MERGE ran zero times. The query
            # completed without error -- that is not evidence the edge was written.
            raise LookupError(
                f"upsert_edge: no endpoint found for tenant {operation.tenant_id!r} "
                f"(from={operation.from_id!r}, to={operation.to_id!r})"
            )

    def count_nodes(self, operation: CountNodes) -> int:
        cypher, params = operation.to_cypher()

        def _read(tx: neo4j.ManagedTransaction) -> int:
            result = tx.run(cypher, params)
            record = result.single()
            count: int = record["c"] if record is not None else 0
            return count

        with self._driver.session() as session:
            return session.execute_read(_read)
