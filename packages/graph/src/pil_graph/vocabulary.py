"""The ITKG closed vocabulary — 10 node labels, 13 edge types.

Ported from AXO's ``packages/itkg/vocab.go`` (``idiaz-io/Axo``, branch
``merp-integration``, PR #47, commit ``b04cae7``) — same names, same literal
string values. These are real Neo4j labels and relationship types, not
language-specific identifiers, so a graph built by one implementation has to
be describable by the other; renaming a member here without renaming it
there would silently split the graph in two.

Source of the vocabulary itself: ``MERP-Agent-Handover.md`` §6.1–6.2 — marked
**DRAFT, ratify via ADR-08 before Epic 1 exit** in that document, still open.
AXO's own ``vocab.go`` comment calls these "the ratified draft types...
(ADR-0008)", citing AXO's *own*, unrelated, four-digit ADR-0008 (the QUILL
keep/refactor decision) — not the same ADR as the handover's own two-digit
``ADR-08``, which has not ratified this. This module doesn't repeat that
overclaim: the vocabulary below is faithfully transcribed, its ratification
status is not asserted.

Closed (I-6): extend by adding a property to an operation in
:mod:`pil_graph.operations`, never by adding a member here. Per ADR-0011,
**a change to either language's copy of this vocabulary requires the
identical change to the other, in the same reviewed change set** — this
module and AXO's ``vocab.go`` are not independently maintained. Each side
pins its own member count (:data:`NODE_LABEL_COUNT`, :data:`EDGE_TYPE_COUNT`)
so a one-sided addition fails its own CI rather than silently drifting until
someone notices in production.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

__all__ = ["EDGE_TYPE_COUNT", "NODE_LABEL_COUNT", "EdgeType", "NodeLabel"]


class NodeLabel(StrEnum):
    """A Neo4j label. The set is closed — see the module docstring."""

    TENANT = "Tenant"
    MISSION = "Mission"
    ASSET = "Asset"
    IDENTITY = "Identity"
    APPLICATION = "Application"
    CONTROL = "Control"
    ARTIFACT = "Artifact"
    FINDING = "Finding"
    CHANGE_RECORD = "ChangeRecord"
    ATTESTATION = "Attestation"


#: Pinned so an addition on this side alone fails CI (ADR-0011) rather than
#: silently drifting from AXO's ``vocab.go``, which pins the same number.
NODE_LABEL_COUNT: Final = 10


class EdgeType(StrEnum):
    """A Neo4j relationship type. The set is closed — see the module docstring."""

    RUNS_ON = "RUNS_ON"
    DEPENDS_ON = "DEPENDS_ON"
    OWNED_BY = "OWNED_BY"
    ATTESTS_TO = "ATTESTS_TO"
    SATISFIES = "SATISFIES"
    VIOLATES = "VIOLATES"
    REMEDIATED_BY = "REMEDIATED_BY"
    DERIVED_FROM = "DERIVED_FROM"
    SIGNED_BY = "SIGNED_BY"
    ESCALATES_TO = "ESCALATES_TO"
    BELONGS_TO_TENANT = "BELONGS_TO_TENANT"
    COVERS_MISSION = "COVERS_MISSION"
    IMPACTS = "IMPACTS"


#: Pinned for the same reason as :data:`NODE_LABEL_COUNT`.
EDGE_TYPE_COUNT: Final = 13
