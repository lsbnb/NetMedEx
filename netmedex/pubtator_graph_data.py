"""Intermediate Representations for PubTator Annotations"""

import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass

from typing_extensions import override

from netmedex.pubtator_data import ANNOTATION_TYPES, PubTatorAnnotation

logger = logging.getLogger(__name__)


@dataclass
class MeshNode:
    mesh: str
    type: str
    name: defaultdict[str, int]
    pmid: str


@dataclass
class PubTatorNode:
    mesh: str
    type: str
    name: str
    pmid: str


@dataclass
class PubTatorEdge:
    node1_id: str
    node2_id: str
    pmid: str
    relation: str


class NodeCollection(ABC):
    @abstractmethod
    def add_node(self, annotation: PubTatorAnnotation) -> None:
        pass

    @abstractmethod
    def to_clean_pubtator_nodes(self) -> dict[str, PubTatorNode]:
        pass


class NonMeshNodeCollection(NodeCollection):
    nodes: dict[str, PubTatorNode]
    node_id_occurrences: defaultdict[str, int]
    node_names: defaultdict[str, set[str]]
    """For removing nodes with the same name but annotated as different types
        {standardized_name : {node_id, ...}}"""

    def __init__(self) -> None:
        self.nodes = {}
        self.node_id_occurrences = defaultdict(int)
        self.node_names = defaultdict(set)

    @override
    def add_node(self, annotation: PubTatorAnnotation) -> None:
        # Normalize text
        name = annotation.get_standardized_name()

        # Text can take on different types depending on the context
        # Append annotation type as suffix
        node_id = annotation.get_non_mesh_node_id(name)
        self.node_id_occurrences[node_id] += 1
        self.node_names[name].add(node_id)

        if node_id not in self.nodes:
            self.nodes[node_id] = PubTatorNode(
                mesh=annotation.mesh,
                type=annotation.type,
                name=name,
                pmid=annotation.pmid,
            )

    @override
    def to_clean_pubtator_nodes(self) -> dict[str, PubTatorNode]:
        """Parse and remove redundant nodes

        The initial non-MeSH nodes have the same attributes as the final nodes
        we want. The only cleaning performed here is removing nodes with the
        same name but annotated as different types. It is likely that, in the
        same article, these nodes represent the same entity but are misannotated
        as different types.
        """
        nodes = self.nodes.copy()
        for node_id_set in self.node_names.values():
            if len(node_id_set) > 1:
                # Remove nodes with the same name but annotated as different types
                # Choose the node with the most occurrences
                node_id = max(node_id_set, key=lambda x: self.node_id_occurrences[x])
                for node_id in node_id_set:
                    if node_id != node_id:
                        nodes.pop(node_id)
        return nodes


class MeshNodeCollection(NodeCollection):
    use_mesh_vocabulary: bool
    """Whether the PubTator file has standardized MeSH terms as names"""
    nodes: dict[str, MeshNode]
    node_occurrences: defaultdict[str, int]

    def __init__(self, use_mesh_vocabulary: bool):
        self.use_mesh_vocabulary = use_mesh_vocabulary
        self.nodes = {}
        self.node_occurrences = defaultdict(int)

    @override
    def add_node(self, annotation: PubTatorAnnotation):
        node_id_list = annotation.get_mesh_node_id()
        name = (
            annotation.get_standardized_name() if not self.use_mesh_vocabulary else annotation.name
        )

        for node_id in node_id_list:
            # Node occurrence information are not used for now, but still keep it
            self.node_occurrences[node_id] += 1
            if node_id not in self.nodes:
                self.nodes[node_id] = MeshNode(
                    mesh=annotation.mesh,
                    type=annotation.type,
                    name=defaultdict(int),
                    pmid=annotation.pmid,
                )
            self.nodes[node_id].name[name] += 1

    @override
    def to_clean_pubtator_nodes(self) -> dict[str, PubTatorNode]:
        """Parse and convert MeshNode to PubTatorNode

        MeSH terms are always indexed by their MeSH IDs. If users choose to keep
        the raw text of MeSH terms, we pick the most frequently occurring one
        as the name for each term. If the raw text is already standardized as MeSH
        terms, it will always be selected since there are no other entries in the
        name.
        """
        nodes = {}
        for node_id, node_data in self.nodes.items():
            name: str = max(node_data.name, key=node_data.name.get)  # type: ignore
            nodes[node_id] = PubTatorNode(
                mesh=node_data.mesh,
                type=node_data.type,
                name=name,
                pmid=node_data.pmid,
            )

        return nodes


class PubTatorNodeCollection(NodeCollection):
    mesh_only: bool
    """Only Keep MeSH Nodes"""
    use_mesh_vocabulary: bool
    non_mesh_collection: NonMeshNodeCollection
    mesh_collection: MeshNodeCollection
    _mesh_nodes: dict[str, PubTatorNode]
    _non_mesh_nodes: dict[str, PubTatorNode]
    _nodes: dict[str, PubTatorNode]
    _mesh_updated: bool
    _non_mesh_updated: bool

    def __init__(self, mesh_only: bool, use_mesh_vocabulary: bool):
        self.mesh_only = mesh_only
        self.use_mesh_vocabulary = use_mesh_vocabulary
        self.non_mesh_collection = NonMeshNodeCollection()
        self.mesh_collection = MeshNodeCollection(use_mesh_vocabulary)
        self._mesh_nodes = {}
        self._non_mesh_nodes = {}
        self._nodes = {}
        self._mesh_updated = False
        self._non_mesh_updated = False

    @override
    def add_node(self, annotation: PubTatorAnnotation):
        if annotation.type not in ANNOTATION_TYPES:
            return

        if annotation.mesh in ("-", ""):
            if self.mesh_only:
                return
            self.non_mesh_collection.add_node(annotation)
            self._non_mesh_updated = True
        else:
            self.mesh_collection.add_node(annotation)
            self._mesh_updated = True

    @override
    def to_clean_pubtator_nodes(self) -> dict[str, PubTatorNode]:
        return self.nodes

    @property
    def mesh_nodes(self) -> dict[str, PubTatorNode]:
        if self._mesh_updated:
            self._mesh_nodes = self.mesh_collection.to_clean_pubtator_nodes()
            self._nodes = self._nodes | self._mesh_nodes
            self._mesh_updated = False
        return self._mesh_nodes

    @property
    def non_mesh_nodes(self) -> dict[str, PubTatorNode]:
        if self._non_mesh_updated:
            self._non_mesh_nodes = self.non_mesh_collection.to_clean_pubtator_nodes()
            self._nodes = self._nodes | self._non_mesh_nodes
            self._non_mesh_updated = False
        return self._non_mesh_nodes

    @property
    def nodes(self) -> dict[str, PubTatorNode]:
        if self._mesh_updated or self._non_mesh_updated:
            self._nodes = self.non_mesh_nodes | self.mesh_nodes
        return self._nodes
