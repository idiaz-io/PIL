"""Schema-as-code: the DDL a real graph needs installed once, before first use.

Port of AXO's ``itkg.go`` ``constraintStmts`` — the statement-*generation* half of AXO's
``ApplyConstraints``. Same split ``pil_graph.operations`` already draws for the three
tenant-scoped operations: this module says what the statement is, in portable openCypher
text; a driver is what runs it. Nothing here executes anything or imports a graph-client
library — see :mod:`pil_graph.driver` for why, and :class:`~pil_graph.driver.GraphDriver`
for where installing these statements is required of an implementation.

**The uid-uniqueness constraint is load-bearing, not merely setup.**
:func:`~pil_graph.operations.uid` builds the synthetic key every ``UpsertNode``/
``UpsertEdge`` MERGEs against, and MERGE's guarantee that at most one node exists per key
depends on that key actually being declared unique to the database. Without the
constraint, two ``UpsertNode`` calls racing on the same ``uid`` can each find no match and
each create a node — two nodes sharing one ``uid``, exactly the failure the whole scheme
exists to prevent. A single-threaded, sequential test will not surface this; a real
deployment's concurrent writers will.

The tenant_id index is a performance concern, not a correctness one — ``CountNodes``'s
``{tenant_id: $tenant}`` filter returns the right answer via a label scan with or without
it. AXO installs both as one unit (``ApplyConstraints``); there is no reason to split them
here.

Community-safe by construction (ADR-0007, AXO side): a single-property uniqueness
constraint and a property index, neither Enterprise-only, neither APOC/GDS —
``tests/test_portability.py`` scans this module's output the same way it already scans
every operation's Cypher.
"""

from __future__ import annotations

from pil_graph.vocabulary import NodeLabel

__all__ = ["all_constraint_statements", "constraint_statements"]


def constraint_statements(label: NodeLabel) -> tuple[str, str]:
    """The uid-uniqueness constraint and tenant_id index for one label.

    Port of ``itkg.go``'s ``constraintStmts``. ``IF NOT EXISTS`` makes both idempotent —
    safe to run against a database that already has them installed, the same posture
    every operation's own ``MERGE`` already takes.
    """
    name = label.value.lower()
    return (
        f"CREATE CONSTRAINT {name}_uid IF NOT EXISTS FOR (n:{label.value}) REQUIRE n.uid IS UNIQUE",
        f"CREATE INDEX {name}_tenant IF NOT EXISTS FOR (n:{label.value}) ON (n.tenant_id)",
    )


def all_constraint_statements() -> tuple[str, ...]:
    """Every statement needed across the whole closed vocabulary — one label's pair,
    repeated for all ten (:data:`~pil_graph.vocabulary.NODE_LABEL_COUNT`)."""
    return tuple(stmt for label in NodeLabel for stmt in constraint_statements(label))
