"""The closed vocabulary — mirrors AXO's ``TestVocabularyIsClosed`` (``itkg_test.go``).

ADR-0011: a change to either language's copy requires the identical change to
the other. This test is half of that guarantee — it fails if this side drifts
from the pinned counts, whether or not AXO's side was updated to match.
"""

from __future__ import annotations

import pytest

from pil_graph.vocabulary import EDGE_TYPE_COUNT, NODE_LABEL_COUNT, EdgeType, NodeLabel


def test_node_label_count_is_pinned() -> None:
    assert len(NodeLabel) == NODE_LABEL_COUNT == 10


def test_edge_type_count_is_pinned() -> None:
    assert len(EdgeType) == EDGE_TYPE_COUNT == 13


def test_known_node_label_accepted() -> None:
    assert NodeLabel("Asset") is NodeLabel.ASSET


def test_known_edge_type_accepted() -> None:
    assert EdgeType("DEPENDS_ON") is EdgeType.DEPENDS_ON


def test_unknown_node_label_rejected() -> None:
    with pytest.raises(ValueError, match="NotALabel"):
        NodeLabel("NotALabel")


def test_unknown_edge_type_rejected() -> None:
    with pytest.raises(ValueError, match="NOT_AN_EDGE"):
        EdgeType("NOT_AN_EDGE")


def test_node_labels_match_the_handover_and_axo_exactly() -> None:
    """§6.1 / AXO's vocab.go, same order, same values — not just the same count."""
    assert [member.value for member in NodeLabel] == [
        "Tenant",
        "Mission",
        "Asset",
        "Identity",
        "Application",
        "Control",
        "Artifact",
        "Finding",
        "ChangeRecord",
        "Attestation",
    ]


def test_edge_types_match_the_handover_and_axo_exactly() -> None:
    """§6.2 / AXO's vocab.go, same order, same values."""
    assert [member.value for member in EdgeType] == [
        "RUNS_ON",
        "DEPENDS_ON",
        "OWNED_BY",
        "ATTESTS_TO",
        "SATISFIES",
        "VIOLATES",
        "REMEDIATED_BY",
        "DERIVED_FROM",
        "SIGNED_BY",
        "ESCALATES_TO",
        "BELONGS_TO_TENANT",
        "COVERS_MISSION",
        "IMPACTS",
    ]
