from collections.abc import Sequence
from dataclasses import dataclass


@dataclass
class GraphNodeData:
    _id: str
    color: str
    label_color: str
    shape: str
    type: str
    name: str
    document_frequency: int
    marked: bool = False
    parent: str | None = None
    pos: Sequence[float] | None = None


@dataclass
class GraphEdgeData:
    _id: str
    raw_frequency: int
    doc_weighted_frequency: float
    npmi: float
    edge_weight: float
    pmids: list[str]
    scaled_edge_weight: float | None = None
    edge_width: int | None = None


@dataclass
class CommunityEdgeData:
    _id: int
    edge_weight: float
    scaled_edge_weight: float
    edge_width: int
    pmids: list[str]
