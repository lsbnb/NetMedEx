import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from netmedex.headers import USE_MESH_VOCABULARY
from netmedex.stemmers import s_stemmer

HEADER_SYMBOL = "##"
MUTATION_PATTERNS = {
    "tmvar": re.compile(r"(tmVar:[^;]+)"),
    "hgvs": re.compile(r"(HGVS:[^;]+)"),
    "rs": re.compile(r"(RS#:[^;]+)"),
    "variantgroup": re.compile(r"(VariantGroup:[^;]+)"),
    "gene": re.compile(r"(CorrespondingGene:[^;]+)"),
    "species": re.compile(r"(CorrespondingSpecies:[^;]+)"),
    "ca": re.compile(r"(CA#:[^;]+)"),
}

ANNOTATION_TYPES = {
    "Chemical",
    "Gene",
    "Species",
    "Disease",
    "DNAMutation",
    "ProteinMutation",
    "CellLine",
    "SNP",
    # "Chromosome",  # Exclude Chromosome
}

logger = logging.getLogger(__name__)


@dataclass
class PubTatorAnnotation:
    pmid: str
    start: int
    end: int
    name: str
    identifier_name: str | None
    type: str
    mesh: str

    def get_standardized_name(self) -> str:
        return s_stemmer(self.name.strip().lower())

    def get_non_mesh_node_id(self, standardized_name: str) -> str:
        """Generate the node ID for a non-MeSH term"""
        # Use lowercase suffix to avoid collisions with mesh IDs (rarely, but sometimes happens)
        return f"{standardized_name}_{self.type.lower()}"

    @staticmethod
    def get_name_from_non_mesh_node_id(node_id: str) -> str:
        return node_id.split("_")[0]

    def get_mesh_node_id(self) -> list[str]:
        """Generate the node ID for a MeSH term

        Genes can have multiple MeSH terms, so always return a list.
        We view genes with mulitple MeSH terms as having multiple identities.
        """
        if self.type == "Gene":
            mesh_list = [f"{mesh}_{self.type}" for mesh in self.mesh.split(";")]
        else:
            mesh_list = [f"{self.mesh}_{self.type}"]

        return mesh_list

    @staticmethod
    def get_mesh_from_mesh_node_id(node_id: str) -> str:
        return node_id.split("_")[0]


@dataclass
class PubTatorRelation:
    pmid: str
    relation_type: str
    mesh1: str
    name1: str | None
    mesh2: str
    name2: str | None


class PubTatorLine:
    @staticmethod
    def parse(line: str) -> PubTatorAnnotation | PubTatorRelation | None:
        instance = None
        data = line.strip("\n").split("\t")
        if len(data) == 6:
            instance = PubTatorAnnotation(
                pmid=data[0],
                start=int(data[1]),
                end=int(data[2]),
                name=data[3],
                identifier_name=None,
                type=data[4],
                mesh=data[5],
            )
        elif len(data) == 4:
            instance = PubTatorRelation(
                pmid=data[0],
                relation_type=data[1],
                mesh1=data[2],
                name1=None,
                mesh2=data[3].split(";")[0],
                name2=None,
            )
        return instance


@dataclass
class PubTatorArticle:
    pmid: str
    date: str | None
    journal: str | None
    title: str
    abstract: str | None
    annotations: list[PubTatorAnnotation]
    relations: list[PubTatorRelation]
    identifiers: dict[str, str | None] | None = None
    metadata: dict[str, str] | None = None

    def to_pubtator_str(
        self,
        annotation_use_identifier_name: bool = True,
        relation_use_identifier: bool = True,
    ):
        title_str = f"{self.pmid}|t|{self.title}\n"
        abstract_str = f"{self.pmid}|a|{self.abstract}\n"
        annotation_str = [
            (
                f"{self.pmid}\t"
                f"{annotation.start}\t"
                f"{annotation.end}\t"
                f"{annotation.identifier_name if annotation_use_identifier_name else annotation.name}\t"
                f"{annotation.type}\t"
                f"{annotation.mesh}"
            )
            for annotation in self.annotations
        ]
        relation_str = [
            (
                f"{self.pmid}\t"
                f"{relation.relation_type}\t"
                f"{relation.mesh1 if relation_use_identifier else relation.name1}\t"
                f"{relation.mesh2 if relation_use_identifier else relation.name2}"
            )
            for relation in self.relations
        ]

        pubtator_str = title_str + abstract_str
        if len(annotation_str) > 0:
            pubtator_str += "\n".join(annotation_str) + "\n"
        if len(relation_str) > 0:
            pubtator_str += "\n".join(relation_str) + "\n"

        return pubtator_str


@dataclass
class PubTatorCollection:
    headers: list[str]
    articles: list[PubTatorArticle]
    metadata: dict[str, Any] = field(default_factory=dict)
    num_articles: int = field(init=False)

    def __post_init__(self):
        self.num_articles = len(self.articles)

    def __repr__(self) -> str:
        return f"PubTatorCollection(num_articles={self.num_articles})"

    def to_pubtator_str(
        self,
        annotation_use_identifier_name: bool = True,
        relation_use_identifier: bool = True,
    ):
        headers = []
        if annotation_use_identifier_name:
            headers.append(USE_MESH_VOCABULARY)

        pubtator_str = ""
        if len(headers) > 0:
            pubtator_str += "\n".join([HEADER_SYMBOL + header for header in headers]) + "\n"
        pubtator_str += "\n".join(
            article.to_pubtator_str(annotation_use_identifier_name, relation_use_identifier)
            for article in self.articles
        )

        return pubtator_str


class PubTatorRelationParser:
    _mesh_node_id_mapping: dict[str, str]
    """{mesh: node_id} mapping for non-mutation terms"""
    _mutation_mesh_node_info: dict[str, dict[str, str | None]]
    """{node_id: mutation_info} for parsing mutation terms"""

    def __init__(self, mesh_node_ids: Sequence[str]) -> None:
        self._mesh_node_id_mapping = {}
        self._mutation_mesh_node_info = {}

        for mesh_node_id in mesh_node_ids:
            if len(mesh_node_id.split(";", 1)) == 1:
                self._mesh_node_id_mapping[
                    PubTatorAnnotation.get_mesh_from_mesh_node_id(mesh_node_id)
                ] = mesh_node_id
            else:
                # Likely a mutation term
                self._mutation_mesh_node_info[mesh_node_id] = self._get_mutation_info(
                    PubTatorAnnotation.get_mesh_from_mesh_node_id(mesh_node_id)
                )

    @staticmethod
    def _get_mutation_info(mesh: str) -> dict[str, str | None]:
        mutation_info = {}
        for name, pattern in MUTATION_PATTERNS.items():
            if (matched := pattern.search(mesh)) is not None:
                mutation_info[name] = matched.group(1)
            else:
                mutation_info[name] = None

        return mutation_info

    def parse(self, relation: PubTatorRelation) -> tuple[str, str] | None:
        """Parse a relation and return the node IDs of the two nodes"""
        nodes = []
        for mesh in (relation.mesh1, relation.mesh2):
            node = self._mesh_node_id_mapping.get(mesh, self.match_mutation_mesh(mesh))
            if node is None:
                logger.warning(f"Mutation not found: {mesh} (PMID: {relation.pmid})")
                return
            nodes.append(node)

        if nodes[0] <= nodes[1]:
            return tuple(nodes)
        else:
            return tuple(reversed(nodes))

    def match_mutation_mesh(self, mesh: str) -> str | None:
        matched_node_id = None
        mutation_info = self._get_mutation_info(mesh)
        for node_id, info_to_match in self._mutation_mesh_node_info.items():
            is_matched = True
            for attr, value in mutation_info.items():
                if value is None:
                    continue
                if info_to_match[attr] != value:
                    is_matched = False
                    break
            if is_matched:
                matched_node_id = node_id
                break

        return matched_node_id
