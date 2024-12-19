import logging
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from netmedex.stemmers import s_stemmer
from netmedex.utils import generate_uuid

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

logger = logging.getLogger(__name__)


@dataclass
class PubTatorNodeData:
    id: str
    mesh: str
    type: str
    name: str | defaultdict[str, int]
    pmids: set[str]


@dataclass
class PubTatorEdgeData:
    id: str
    pmid: str
    relation: str | None = None


@dataclass
class PubTatorAnnotation:
    pmid: str
    start: str
    end: str
    name: str
    type: str
    mesh: str


@dataclass
class PubTatorRelation:
    pmid: str
    relation: str
    mesh1: str
    mesh2: str


class PubTatorLine:
    use_mesh = False

    def __init__(self, line: str):
        self.values: list[str] = [value.strip() for value in line.split("\t")]
        self.type: str = self.assign_line_type(self.values)
        self._data: PubTatorAnnotation | PubTatorRelation | None = None

    @staticmethod
    def assign_line_type(values: Sequence):
        if len(values) == 4:
            return "relation"
        elif len(values) == 6:
            return "annotation"
        else:
            return "unknown"

    @property
    def data(self):
        if self._data is None:
            self._data = self.parse_line()
        return self._data

    def parse_line(self):
        if self.type == "annotation":
            data = PubTatorAnnotation(*self.values)
        elif self.type == "relation":
            data = PubTatorRelation(*self.values)
        else:
            data = None
        return data

    def normalize_name(self):
        self.data.name = s_stemmer(self.data.name.lower())

    def parse_mesh(self, mesh_map: Mapping[str, str]):
        def convert_mesh(mesh: str, type_: str):
            converted = f"{type_}_{mesh}"
            if mesh not in mesh_map:
                mesh_map[mesh] = converted
            return converted

        anno_type = self.data.type
        mesh = self.data.mesh

        if not self.use_mesh:
            self.normalize_name()

        if anno_type in ("DNAMutation", "ProteinMutation", "SNP"):
            match_data = {}
            for key, pattern in MUTATION_PATTERNS.items():
                try:
                    match_data[key] = f"{re.search(pattern, mesh).group(1)};"
                except AttributeError:
                    match_data[key] = ""
            if anno_type == "DNAMutation":
                mesh = (
                    f'{match_data["gene"]}{match_data["species"]}{match_data["variantgroup"]}'
                    f'{match_data["tmvar"].split("|")[0]}'
                ).strip(";")
            elif anno_type == "ProteinMutation":
                mesh = f'{match_data["rs"]}{match_data["hgvs"]}{match_data["gene"]}'.strip(";")
            elif anno_type == "SNP":
                mesh = f'{match_data["rs"]}{match_data["hgvs"]}{match_data["gene"]}'.strip(";")
            result = [{"key": mesh, "mesh": mesh}]
        elif anno_type == "Gene":
            mesh_list = mesh.split(";")
            result = [{"key": convert_mesh(mesh, "gene"), "mesh": mesh} for mesh in mesh_list]
        elif anno_type == "Species":
            result = [{"key": convert_mesh(mesh, "species"), "mesh": mesh}]
        else:
            result = [{"key": mesh, "mesh": mesh}]

        return result


@dataclass
class PubTatorResult:
    node_dict: dict[str, PubTatorNodeData]
    edge_dict: dict[str, list[PubTatorEdgeData]]
    non_isolated_nodes: set[str]
    num_pmids: int
    pmid_title_map: dict[str, str]


class PubTatorParser:
    def __init__(
        self,
        pubtator_filepath: str,
        node_type: Literal["all", "mesh", "relation"],
    ):
        self.pubtator_file = pubtator_filepath
        self.node_type = node_type
        self._mesh_only: bool = True if node_type in ("mesh", "relation") else False
        self.num_pmids: int = 0
        self.mesh_map: dict[str, str] = {}
        self.pmid_title_map: dict[str, str] = {}
        self.node_dict_each: dict[str, PubTatorNodeData] = {}
        self.node_dict: dict[str, PubTatorNodeData] = {}
        self.edge_dict: defaultdict[str, list[PubTatorEdgeData]] = defaultdict(list)
        self.non_isolated_nodes: set[str] = set()

    def parse(self):
        pmid = -1
        last_pmid = -1
        node_dict_each = {}

        self._parse_header(self.pubtator_file)
        with open(self.pubtator_file) as f:
            for line in f.readlines():
                if self._is_title(line):
                    pmid = self._parse_title(line)
                    self.num_pmids += 1
                    continue
                if self.node_type == "relation":
                    parsed_line = PubTatorLine(line)
                    self._parse_line_relation(parsed_line)
                else:
                    if pmid != last_pmid:
                        self._create_complete_graph(node_dict_each, pmid)
                        last_pmid = pmid
                        node_dict_each = {}
                    parsed_line = PubTatorLine(line)
                    if parsed_line.type == "annotation":
                        self._add_node(parsed_line, node_dict_each)
            self._create_complete_graph(node_dict_each, pmid)
        self._determine_mesh_term_labels()
        self._get_non_isolated_nodes()

        return PubTatorResult(
            node_dict=self.node_dict,
            edge_dict=dict(self.edge_dict),
            non_isolated_nodes=self.non_isolated_nodes,
            num_pmids=self.num_pmids,
            pmid_title_map=self.pmid_title_map,
        )

    def _parse_line_relation(self, line: PubTatorLine):
        if line.type == "annotation":
            self._add_node(line, {})
        elif line.type == "relation":
            self._create_edges_for_relations(line)

    def _add_node(
        self,
        line: PubTatorLine,
        node_dict_each: dict[str, PubTatorNodeData],
    ):
        data = line.data
        if data.mesh in ("-", ""):
            if self._mesh_only:
                return
            # By Text
            line.normalize_name()

            name = data.name
            if not self._node_id_registered(line, name):
                self.node_dict[name] = PubTatorNodeData(
                    id=generate_uuid(), mesh=data.mesh, type=data.type, name=name, pmids=set()
                )
            node_dict_each.setdefault(name, self.node_dict[data.name])
            self.node_dict[name].pmids.add(data.pmid)
        else:
            # By MeSH
            # TODO: better way to deal with unseen MeSH types (e.g. Chromosome)
            if data.type == "Chromosome":
                return

            mesh_list = line.parse_mesh(self.mesh_map)

            for mesh in mesh_list:
                node_id = mesh["key"]
                if not self._node_id_registered(line, node_id):
                    self.node_dict[node_id] = PubTatorNodeData(
                        id=generate_uuid(),
                        mesh=mesh["mesh"],
                        type=data.type,
                        name=defaultdict(int),
                        pmids=set(),
                    )
                node_dict_each.setdefault(node_id, self.node_dict[node_id])
                self.node_dict[node_id].name[data.name] += 1
                self.node_dict[node_id].pmids.add(data.pmid)

    def _create_edges_for_relations(self, line: PubTatorLine):
        data = line.data
        # TODO: better way to deal with DNAMutation notation inconsistency
        mesh_1 = data.mesh1.split("|")[0]
        mesh_1 = self.mesh_map.get(mesh_1, mesh_1)
        mesh_2 = data.mesh2.split("|")[0]
        mesh_2 = self.mesh_map.get(mesh_2, mesh_2)
        self.edge_dict[(mesh_1, mesh_2)].append(
            PubTatorEdgeData(id=generate_uuid(), pmid=data.pmid, relation=data.relation)
        )

    def _node_id_registered(self, line: PubTatorLine, node_id: str):
        is_registered = False
        data = line.data
        if node_id in self.node_dict:
            is_registered = True
            if data.type != self.node_dict[node_id].type:
                info = {
                    "id": node_id,
                    "type": data.type,
                    "name": data.name,
                }
                logger.debug(f"Found collision of MeSH:\n{self.node_dict[node_id]}\n{info}")
                logger.debug("Discard the latter\n")

        return is_registered

    def _create_complete_graph(
        self,
        node_dict_each: dict[str, PubTatorNodeData],
        pmid: str,
    ):
        for i, name_1 in enumerate(node_dict_each.keys()):
            for j, name_2 in enumerate(node_dict_each.keys()):
                if i >= j:
                    continue
                if self.edge_dict.get((name_2, name_1), []):
                    key = (name_2, name_1)
                else:
                    key = (name_1, name_2)
                self.edge_dict[key].append(PubTatorEdgeData(id=generate_uuid(), pmid=pmid))

    def _determine_mesh_term_labels(self):
        def determine_node_label(candidate_name: str):
            nonlocal node_data
            return (node_data.name[candidate_name], -len(candidate_name))

        for node_id, node_data in self.node_dict.items():
            if isinstance(node_data.name, defaultdict):
                # Use the name that appears the most times
                self.node_dict[node_id].name = max(node_data.name, key=determine_node_label)

        self._merge_same_name_genes()

    def _merge_same_name_genes(self):
        gene_name_dict = defaultdict(list)
        for node_id, node_data in self.node_dict.items():
            if node_data.type != "Gene" or node_data.mesh in ("-", ""):
                continue
            gene_name_dict[node_data.name].append(
                {
                    "node_id": node_id,
                    "mesh": node_data.mesh,
                    "pmids": node_data.pmids,
                }
            )

        for node_data_list in gene_name_dict.values():
            mesh_list = []
            edges_to_merge = []
            removed_node_ids = []
            pmid_collection = set()
            for node_data in node_data_list:
                node_id = node_data["node_id"]
                # Nodes
                popped_node_data = self.node_dict.pop(node_id)
                removed_node_ids.append(node_id)
                mesh_list.append(node_data["mesh"])
                for pmid in node_data["pmids"]:
                    pmid_collection.add(pmid)

                # Edges
                for u, v in self.edge_dict.keys():
                    if u == node_id:
                        edges_to_merge.append((u, v, "u"))
                    elif v == node_id:
                        edges_to_merge.append((u, v, "v"))

            # Nodes
            concated_mesh = ";".join(mesh_list)
            # popped_node_data is the last node_data of nodes having the same name
            popped_node_data.mesh = concated_mesh
            popped_node_data.pmids = pmid_collection
            node_key = f"gene_{concated_mesh}"
            self.node_dict[node_key] = popped_node_data

            # Edges
            merged_edges = defaultdict(list)
            for u, v, pos in edges_to_merge:
                neighbor = v if pos == "u" else u
                try:
                    popped_edge_data = self.edge_dict.pop((u, v))
                except KeyError:
                    # The same gene but given different ids in the same article
                    assert neighbor in removed_node_ids
                if neighbor in removed_node_ids:
                    continue
                merged_edges[(node_key, neighbor)].extend(popped_edge_data)
            self.edge_dict.update(merged_edges)

    def _get_non_isolated_nodes(self):
        if self.node_type in ("all", "mesh"):
            self.non_isolated_nodes = set(self.node_dict.keys())
        elif self.node_type == "relation":
            for node_1, node_2 in self.edge_dict:
                self.non_isolated_nodes.add(node_1)
                self.non_isolated_nodes.add(node_2)

    def _parse_title(self, line: str):
        pmid, title = line.split("|t|")
        self.pmid_title_map.setdefault(pmid, title)
        return pmid

    @staticmethod
    def _is_title(line: str):
        return line.find("|t|") != -1

    @staticmethod
    def _parse_header(filepath: str):
        PubTatorLine.use_mesh = False
        with open(filepath) as f:
            for line in f.readlines():
                if not line.startswith(HEADER_SYMBOL):
                    break
                PubTatorParser._assign_flags(line.replace(HEADER_SYMBOL, "", 1).strip())

    @staticmethod
    def _assign_flags(line: str):
        if line == "USE-MESH-VOCABULARY":
            PubTatorLine.use_mesh = True
