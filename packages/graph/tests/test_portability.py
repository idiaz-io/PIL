"""openCypher portability — mirrors AXO's ``TestOpenCypherPortability``
(``itkg_test.go``). No APOC/GDS/Enterprise-only construct anywhere in this
package's own source, and none in the Cypher text a real operation actually
produces — so the same code stays portable to Neo4j Community, Memgraph, or
AGE (ADR-01, AXO side; the same constraint this package inherits by porting
AXO's design rather than reinventing it, per ADR-0011).
"""

from __future__ import annotations

from pathlib import Path

from pil_graph.operations import CountNodes, UpsertEdge, UpsertNode
from pil_graph.vocabulary import EdgeType, NodeLabel

#: Same banned-construct list AXO's test uses. "NODE KEY" and existence
#: constraints are Enterprise-only; APOC/GDS calls aren't available on
#: Community or Memgraph/AGE either.
BANNED = ("apoc.", "gds.", "NODE KEY", "IS NOT NULL", "IS :: ")

SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "pil_graph"


def test_no_source_file_uses_a_non_portable_construct() -> None:
    offenders: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for bad in BANNED:
            if bad in text:
                offenders.append(f"{path.name} contains non-portable construct {bad!r}")
    assert not offenders, "\n".join(offenders)


def test_upsert_node_cypher_is_portable() -> None:
    cypher, _ = UpsertNode(tenant_id="t", label=NodeLabel.ASSET, id="x").to_cypher()
    for bad in BANNED:
        assert bad not in cypher, f"UpsertNode Cypher contains {bad!r}"


def test_upsert_edge_cypher_is_portable() -> None:
    cypher, _ = UpsertEdge(
        tenant_id="t",
        edge_type=EdgeType.RUNS_ON,
        from_label=NodeLabel.ASSET,
        from_id="a",
        to_label=NodeLabel.MISSION,
        to_id="b",
    ).to_cypher()
    for bad in BANNED:
        assert bad not in cypher, f"UpsertEdge Cypher contains {bad!r}"


def test_count_nodes_cypher_is_portable() -> None:
    cypher, _ = CountNodes(tenant_id="t", label=NodeLabel.ASSET).to_cypher()
    for bad in BANNED:
        assert bad not in cypher, f"CountNodes Cypher contains {bad!r}"
