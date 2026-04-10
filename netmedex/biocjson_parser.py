from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import datetime
from typing import Any

from netmedex.pubtator_data import PubTatorAnnotation, PubTatorArticle, PubTatorRelation

logger = logging.getLogger(__name__)

DOI_PATTERN = re.compile(r"doi:\s?(10\.\d{4,}/[\S]+)\.", re.IGNORECASE)
JOURNAL_REF_PATTERN = re.compile(r";(\d+)(?:\(([^)]+)\))?:([^.\s;]+)")


def parse_journal_info(journal_str: str) -> dict[str, str | None]:
    """Parse PubMed journal string for Journal Name, Volume, Issue, and Pages."""
    info = {"journal_name": None, "volume": None, "issue": None, "pages": None}
    if not journal_str:
        return info

    # Example: "Breast Cancer Res. 2012 Mar 19;14(2):R50. doi: 10.1186/bcr3151."
    # 1. Try to find volume, issue, pages via pattern
    match = JOURNAL_REF_PATTERN.search(journal_str)
    if match:
        info["volume"] = match.group(1)
        info["issue"] = match.group(2)
        info["pages"] = match.group(3)

    # 2. Extract Journal Name and Date part
    # Split by the first semicolon found (start of volume/issue/pages)
    main_part = journal_str.split(";", 1)[0].strip()
    if "." in main_part:
        # Standard PubMed: Journal. Year Mon Day;
        # We take the part before the last period as the journal name.
        last_period_idx = main_part.rfind(".")
        info["journal_name"] = main_part[:last_period_idx].strip()
    else:
        info["journal_name"] = main_part

    return info


def biocjson_to_pubtator(
    res_json: dict[str, Any],
    full_text: bool = False,
) -> list[PubTatorArticle]:
    """Parse the response from the PubTator3 API in BioC-JSON format.

    Args:
        res_json (dict[str, Any]):
            The response from the PubTator3 API in BioC-JSON format.
        full_text (bool):
            Whether to request full-text annotations (available only in `biocjson`). Defaults to False.

    Returns:
        list[PubTatorArticle]:
            A list of PubTatorArticle objects.
    """
    try:
        return _biocjson_to_pubtator(res_json, full_text=full_text)
    except Exception as e:
        logger.error(f"Failed to parse BioC-JSON response. Reason: {e}")

    return []


def _biocjson_to_pubtator(
    res_json,
    full_text: bool = False,
) -> list[PubTatorArticle]:
    res_json = res_json["PubTator3"]

    output = []
    for each_res_json in res_json:
        pmid = str(each_res_json["pmid"])

        title_passage = extract_passage(each_res_json, "TITLE")
        abstract_passage = extract_passage(each_res_json, "ABSTRACT")

        # metadata extraction
        infons = each_res_json["passages"][0]["infons"] if each_res_json["passages"] else {}

        # Prefer passage infons for full citation string
        journal_raw = infons.get("journal") or each_res_json.get("journal")
        date_str = each_res_json.get("date") or infons.get("date")

        date = None
        if date_str is not None:
            try:
                # Handle both "YYYY-MM-DDTHH:MM:SSZ" and "YYYY" or "YYYY Mon DD"
                if "T" in date_str:
                    date = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%d")
                else:
                    date = date_str  # Keep as is if it's already a simple date
            except Exception:
                date = date_str

        if (not date or date == "None") and infons.get("year"):
            date = infons.get("year")

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

        # doi
        doi = None
        try:
            # Abstract only biocjson file
            if "journal" in infons and (match := DOI_PATTERN.search(infons["journal"])) is not None:
                doi = match.group(1)
        except Exception:
            # Full-text biocjson file
            try:
                doi = infons.get("article-id_doi")
            except Exception:
                pass

        # volume, issue, pages, journal_name
        vol_issue_pages = parse_journal_info(journal_raw or "")
        journal = vol_issue_pages["journal_name"] or journal_raw
        volume = infons.get("volume") or vol_issue_pages["volume"]
        issue = infons.get("issue") or vol_issue_pages["issue"]
        pages = infons.get("pages") or vol_issue_pages["pages"]

        # authors
        authors = each_res_json.get("authors")
        if not authors:
            try:
                # Try from infons
                authors = infons.get("authors")
            except Exception:
                pass
        
        # If still not found, check all passages for an 'author' section
        if not authors:
            for passage in each_res_json.get("passages", []):
                if passage.get("infons", {}).get("type", "").lower() == "author":
                    authors = passage.get("text")
                    if authors:
                        break

        output.append(
            PubTatorArticle(
                pmid=pmid,
                date=date,
                journal=journal,
                doi=doi,
                volume=volume,
                issue=issue,
                pages=pages,
                title=title,
                abstract=abstract,
                annotations=annotation_list,
                relations=relation_list,
                identifiers={
                    annotation.mesh: annotation.identifier_name
                    for annotation in annotation_list
                    if annotation.mesh != "-"
                },
                metadata={"authors": authors} if authors else None,
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
            try:
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
            except Exception:
                logger.warning(f"Failed to parse annotation: {annotation_entry}")

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
        try:
            each_relation = {}
            each_relation["role1"] = relation_entry["infons"]["role1"]["identifier"]
            each_relation["name1"] = relation_entry["infons"]["role1"]["name"]
            each_relation["role2"] = relation_entry["infons"]["role2"]["identifier"]
            each_relation["name2"] = relation_entry["infons"]["role2"]["name"]
            each_relation["type"] = relation_entry["infons"]["type"]
            relation_list.append(each_relation)
        except Exception:
            logger.warning(f"Failed to parse relation: {relation_entry['infons']}")

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
