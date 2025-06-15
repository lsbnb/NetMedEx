from collections.abc import Sequence
from dataclasses import dataclass

NODE_COLOR_MAP = {
    "Chemical": "#67A9CF",
    "Gene": "#74C476",
    "Species": "#FD8D3C",
    "Disease": "#8C96C6",
    "DNAMutation": "#FCCDE5",
    "ProteinMutation": "#FA9FB5",
    "CellLine": "#BDBDBD",
    "SNP": "#FFFFB3",
}
NODE_SHAPE_MAP = {
    "Chemical": "ELLIPSE",
    "Gene": "TRIANGLE",
    "Species": "DIAMOND",
    "Disease": "ROUNDRECTANGLE",
    "DNAMutation": "PARALLELOGRAM",
    "ProteinMutation": "HEXAGON",
    "CellLine": "VEE",
    "SNP": "OCTAGON",
}


@dataclass
class GraphNode:
    _id: str
    color: str
    label_color: str
    shape: str
    type: str
    mesh: str
    name: str
    pmids: set[str]
    num_articles: int | None = None
    weighted_num_articles: float | None = None
    marked: bool = False
    parent: str | None = None
    pos: Sequence[float] | None = None


@dataclass
class GraphEdge:
    _id: str
    relations: dict[str, set[str]]
    type: str
    num_relations: int | None = None
    weighted_num_relations: float | None = None
    npmi: float | None = None
    edge_weight: float | None = None
    edge_width: float | None = None


@dataclass
class CommunityEdge:
    _id: str
    type: str
    edge_weight: float
    pmids: set[str]
    edge_width: float | None = None
