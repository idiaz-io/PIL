"""pil_graph_writer — project a translated Envelope onto ITKG graph operations.

Depends only on ``pil_contracts`` (the Envelope) and ``pil_graph`` (the operations,
vocabulary, and driver interface) — nothing here knows about any vendor or translator.
Ships no execution: :func:`project` returns operations, a
:class:`~pil_graph.driver.GraphDriver` runs them. Wiring this into the translation path is
``pil_adapters.sink.GraphSink``'s job, not this package's.
"""

from pil_graph_writer.identity import (
    MISSING_ALERT_ID_SENTINELS,
    is_missing_alert_id,
    node_id_for,
)
from pil_graph_writer.project import project

__all__ = [
    "MISSING_ALERT_ID_SENTINELS",
    "is_missing_alert_id",
    "node_id_for",
    "project",
]
