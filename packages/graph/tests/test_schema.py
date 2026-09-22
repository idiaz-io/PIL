"""Schema-as-code — port of AXO's ``constraintStmts`` (``itkg.go``).

Pure text generation, checked without a live database — the same posture
``test_operations.py`` already takes toward ``to_cypher()``.
"""

from __future__ import annotations

from pil_graph.schema import all_constraint_statements, constraint_statements
from pil_graph.vocabulary import NODE_LABEL_COUNT, NodeLabel


def test_constraint_statements_for_one_label() -> None:
    uid_stmt, tenant_stmt = constraint_statements(NodeLabel.ASSET)
    assert "CONSTRAINT asset_uid" in uid_stmt
    assert "FOR (n:Asset)" in uid_stmt
    assert "REQUIRE n.uid IS UNIQUE" in uid_stmt
    assert "INDEX asset_tenant" in tenant_stmt
    assert "FOR (n:Asset)" in tenant_stmt
    assert "ON (n.tenant_id)" in tenant_stmt


def test_constraint_statements_are_idempotent() -> None:
    """``IF NOT EXISTS`` on both — safe to apply against a database that already has
    them, the same posture every operation's own MERGE already takes."""
    for statement in constraint_statements(NodeLabel.MISSION):
        assert "IF NOT EXISTS" in statement


def test_all_constraint_statements_covers_every_label() -> None:
    """Two statements per label, all ten — not a hand-maintained subset."""
    statements = all_constraint_statements()
    assert len(statements) == NODE_LABEL_COUNT * 2
    for label in NodeLabel:
        name = label.value.lower()
        assert any(f"{name}_uid" in s for s in statements), f"missing uid constraint for {label}"
        assert any(f"{name}_tenant" in s for s in statements), f"missing tenant index for {label}"


def test_constraint_statement_uses_the_label_actually_passed() -> None:
    """Not hardcoded to one label — a wrong label here would silently protect the
    wrong node type."""
    uid_stmt, _ = constraint_statements(NodeLabel.IDENTITY)
    assert "Identity" in uid_stmt
    assert "Asset" not in uid_stmt
