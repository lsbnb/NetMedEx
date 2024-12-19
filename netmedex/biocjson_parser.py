import logging
from collections import defaultdict
from typing import Literal

logger = logging.getLogger(__name__)


def biocjson_to_pubtator(
    res_json,
    retain_ori_text: bool = True,
    only_abstract: bool = False,
    role_type: Literal["identifier", "name"] = "identifier",
):
    # 2024/05/26: PubTator has changed the format of the response
    res_json = res_json["PubTator3"]

    converted_strs = []
    for each_res_json in res_json:
        pmid = each_res_json["pmid"]

        title_passage = extract_passage(each_res_json, "TITLE")
        abstract_passage = extract_passage(each_res_json, "ABSTRACT")

        if not title_passage or not abstract_passage:
            continue

        if only_abstract:
            abstract_idx = title_passage["idx"] + abstract_passage["idx"]
        else:
            abstract_idx = None

        annotation_list = get_biocjson_annotations(
            each_res_json, retain_ori_text, abstract_idx=abstract_idx
        )
        relation_list = get_biocjson_relations(each_res_json, role_type)
        converted_strs.append(
            create_pubtator_str(
                pmid,
                # Only one title passage
                title_passage["text"][0],
                " ".join(abstract_passage["text"]),
                annotation_list,
                relation_list,
            )
        )

    return "".join(converted_strs)


def extract_passage(content, name):
    passage_info = defaultdict(list)
    # "section_type" exists if the article has full text
    try:
        content["passages"][0]["infons"]["section_type"]
        section_type = "section_type"
    except KeyError:
        section_type = "type"
        name = name.lower()

    for idx, passage in enumerate(content["passages"]):
        if passage["infons"][section_type] == name:
            passage_json = content["passages"][idx]
            passage_idx = idx
            passage_info["text"].append(passage_json["text"])
            passage_info["idx"].append(passage_idx)

    return passage_info


def get_biocjson_annotations(res_json, retain_ori_text, abstract_idx=None):
    n_passages = len(res_json["passages"])

    annotation_list = []
    # TODO: extract from specific passages only (if full_text)?
    if abstract_idx:
        passages = [res_json["passages"][i]["annotations"] for i in abstract_idx]
    else:
        passages = [res_json["passages"][i]["annotations"] for i in range(n_passages)]
    for annotation_entries in passages:
        for annotation_entry in annotation_entries:
            annotation = {}
            try:
                id = annotation_entry["infons"]["identifier"]
            except Exception:
                id = "-"
            annotation["id"] = "-" if id == "None" or id is None else id
            annotation["type"] = annotation_entry["infons"]["type"]
            annotation["locations"] = annotation_entry["locations"][0]
            annotation["name"] = get_name(retain_ori_text, annotation_entry, annotation)
            if annotation["type"] == "Variant":
                annotation["type"] = annotation_entry["infons"]["subtype"]

            if annotation["name"] is None:
                continue
            annotation_list.append(annotation)

    return annotation_list


def get_name(retain_ori_text, annotation_entry, annotation):
    try:
        if retain_ori_text:
            name = annotation_entry["text"]
            # In type == "species", the entity name is stored in "text"
        elif annotation["type"] == "Species":
            name = annotation_entry["text"]
            # Variant can be either SNP, DNAMutation, or ProteinMutation
        elif annotation["type"] == "Variant":
            # Some variants may not have standardized name
            try:
                name = annotation_entry["infons"]["name"]
            except KeyError:
                name = None
        elif annotation_entry["infons"].get("database", "none") == "omim":
            name = annotation_entry["text"]
        else:
            try:
                name = annotation_entry["infons"]["name"]
            except KeyError:
                name = annotation_entry["text"]
    except KeyError as e:
        name = None
        logger.warning(f"Cannot find annotation name: {str(e)}")

    return name


def get_biocjson_relations(res_json, role_type):
    relation_list = []
    for relation_entry in res_json["relations"]:
        each_relation = {}
        each_relation["role1"] = relation_entry["infons"]["role1"][role_type]
        each_relation["role2"] = relation_entry["infons"]["role2"][role_type]
        each_relation["type"] = relation_entry["infons"]["type"]
        relation_list.append(each_relation)

    return relation_list


def create_pubtator_str(pmid, title, abstract, annotation_list, relation_list):
    title_str = f"{pmid}|t|{title}\n"
    abstract_str = f"{pmid}|a|{abstract}\n"
    annotation_list.sort(key=lambda x: x["locations"]["offset"])
    annotation_str = [
        (
            f"{pmid}\t"
            f"{annotation['locations']['offset']}\t"
            f"{annotation['locations']['length'] + annotation['locations']['offset']}\t"
            f"{annotation['name']}\t"
            f"{annotation['type']}\t"
            f"{annotation['id']}"
        )
        for annotation in annotation_list
    ]
    relation_str = [
        (f"{pmid}\t" f"{relation['type']}\t" f"{relation['role1']}\t" f"{relation['role2']}")
        for relation in relation_list
    ]

    return (
        title_str
        + abstract_str
        + "\n".join(annotation_str)
        + "\n"
        + "\n".join(relation_str)
        + "\n\n"
    )
