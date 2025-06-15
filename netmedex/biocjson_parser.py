import logging
from collections import defaultdict
from datetime import datetime
from typing import Any

from netmedex.pubtator_data import PubTatorAnnotation, PubTatorArticle, PubTatorRelation

logger = logging.getLogger(__name__)


def biocjson_to_pubtator(
    res_json,
    full_text: bool = False,
) -> list[PubTatorArticle]:
    res_json = res_json["PubTator3"]

    output = []
    for each_res_json in res_json:
        pmid = each_res_json["pmid"]

        title_passage = extract_passage(each_res_json, "TITLE")
        abstract_passage = extract_passage(each_res_json, "ABSTRACT")
        journal = each_res_json.get("journal")
        date = None
        if (date_str := each_res_json.get("date")) is not None:
            try:
                date = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%d")
            except Exception:
                pass

        if not title_passage or not abstract_passage:
            continue

        if full_text:
            paragraph_indices = None
        else:
            paragraph_indices = title_passage["idx"] + abstract_passage["idx"]

        annotation_list = create_pubtator_annotation(
            pmid=pmid,
            annotation_list=get_biocjson_annotations(
                each_res_json, paragraph_indices=paragraph_indices
            ),
        )
        relation_list = create_pubtator_relation(
            pmid=pmid, relation_list=get_biocjson_relations(each_res_json)
        )

        # Only one title passage
        title = title_passage["text"][0]
        # There may be multiple abstract passages
        abstract = " ".join(abstract_passage["text"])

        output.append(
            PubTatorArticle(
                pmid=pmid,
                date=date,
                journal=journal,
                title=title,
                abstract=abstract,
                annotations=annotation_list,
                relations=relation_list,
                identifiers={
                    annotation.mesh: annotation.identifier_name for annotation in annotation_list
                },
            )
        )

    return output


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


def get_biocjson_annotations(res_json, paragraph_indices=None):
    n_passages = len(res_json["passages"])

    annotation_list: list[dict[str, Any]] = []
    if paragraph_indices:
        passages = [res_json["passages"][i]["annotations"] for i in paragraph_indices]
    else:
        passages = [res_json["passages"][i]["annotations"] for i in range(n_passages)]

    for annotation_entries in passages:
        for annotation_entry in annotation_entries:
            annotation = {}
            try:
                id = annotation_entry["infons"]["identifier"]
            except Exception:
                id = "-"
            annotation["id"] = "-" if id == "None" or not id else id
            annotation["type"] = annotation_entry["infons"]["type"]
            annotation["locations"] = annotation_entry["locations"][0]
            annotation["name"] = annotation_entry["text"]
            annotation["identifier_name"] = get_identifier_name(
                annotation_entry, annotation["type"]
            )
            if annotation["type"] == "Variant":
                annotation["type"] = annotation_entry["infons"]["subtype"]

            if annotation["name"] is None:
                continue
            annotation_list.append(annotation)

    return annotation_list


def get_identifier_name(annotation_entry, annotation_type):
    try:
        if annotation_type == "Species":
            # In type == "species", the entity name is stored in "text"
            name = annotation_entry["text"]
            # Variant can be either SNP, DNAMutation, or ProteinMutation
        elif annotation_type == "Variant":
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


def get_biocjson_relations(res_json):
    relation_list = []
    for relation_entry in res_json["relations"]:
        each_relation = {}
        each_relation["role1"] = relation_entry["infons"]["role1"]["identifier"]
        each_relation["name1"] = relation_entry["infons"]["role1"]["name"]
        each_relation["role2"] = relation_entry["infons"]["role2"]["identifier"]
        each_relation["name2"] = relation_entry["infons"]["role2"]["name"]
        each_relation["type"] = relation_entry["infons"]["type"]
        relation_list.append(each_relation)

    return relation_list


def create_pubtator_annotation(pmid: str, annotation_list: list[dict[str, Any]]):
    return sorted(
        [
            PubTatorAnnotation(
                pmid=pmid,
                start=annotation["locations"]["offset"],
                end=annotation["locations"]["length"] + annotation["locations"]["offset"],
                name=annotation["name"],
                identifier_name=annotation["identifier_name"],
                type=annotation["type"],
                mesh=annotation["id"],
            )
            for annotation in annotation_list
        ],
        key=lambda x: (x.start, x.end),
    )


def create_pubtator_relation(pmid: str, relation_list: list[dict[str, Any]]):
    return [
        PubTatorRelation(
            pmid=pmid,
            relation_type=relation["type"],
            mesh1=relation["role1"],
            name1=relation["name1"],
            mesh2=relation["role2"],
            name2=relation["name2"],
        )
        for relation in relation_list
    ]
