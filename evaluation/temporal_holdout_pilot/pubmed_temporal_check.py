#!/usr/bin/env python3
"""Audit pre-cutoff novelty, then validate frozen candidates in a later window."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"


def request_json(endpoint: str, params: dict[str, str], retries: int = 4) -> dict:
    url = BASE + endpoint + "?" + urllib.parse.urlencode(params)
    last_error = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "NetMedEx-temporal-pilot/1.0"})
            with urllib.request.urlopen(req, timeout=45) as response:
                return json.load(response)
        except Exception as exc:  # pragma: no cover - network dependent
            last_error = exc
            time.sleep(1.0 + attempt)
    raise RuntimeError(f"NCBI request failed: {last_error}")


def search_pair(a: str, c: str) -> list[str]:
    query = f'("{a}"[Title/Abstract]) AND ("{c}"[Title/Abstract])'
    data = request_json(
        "esearch.fcgi",
        {"db": "pubmed", "term": query, "retmode": "json", "retmax": "5000"},
    )
    return data["esearchresult"]["idlist"]


def summaries(pmids: list[str]) -> list[dict]:
    records = []
    for offset in range(0, len(pmids), 150):
        batch = pmids[offset : offset + 150]
        data = request_json(
            "esummary.fcgi",
            {"db": "pubmed", "id": ",".join(batch), "retmode": "json"},
        )["result"]
        for pmid in batch:
            item = data.get(pmid, {})
            match = re.search(r"(?:19|20)\d{2}", item.get("pubdate", ""))
            records.append(
                {
                    "pmid": pmid,
                    "year": int(match.group()) if match else None,
                    "title": item.get("title", ""),
                    "pubdate": item.get("pubdate", ""),
                    "pubtype": item.get("pubtype", []),
                }
            )
        time.sleep(0.35)
    return records


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--mode", choices=("freeze", "validate"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    spec = json.loads(args.candidates.read_text(encoding="utf-8"))
    cutoff = int(spec["cutoff_year"])
    if "validation_window" in spec:
        start, end = (int(value) for value in spec["validation_window"])
    else:
        start = int(spec["validation_start_year"])
        end = int(spec["validation_end_year"])
    output = {
        "mode": args.mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input": str(args.candidates),
        "input_sha256": sha256(args.candidates),
        "cutoff_year": cutoff,
        "validation_window": [start, end],
        "records": [],
    }
    candidates = spec.get("candidates", spec.get("records", []))
    if args.mode == "validate":
        candidates = [candidate for candidate in candidates if candidate.get("eligible_at_cutoff", True)]
    for candidate in candidates:
        all_records = summaries(search_pair(candidate["a_query"], candidate["c_query"]))
        if args.mode == "freeze":
            selected = [r for r in all_records if r["year"] is not None and r["year"] <= cutoff]
        else:
            selected = [r for r in all_records if r["year"] is not None and start <= r["year"] <= end]
        output["records"].append(
            {
                **candidate,
                "all_pair_records": len(all_records),
                "window_record_count": len(selected),
                "window_records": selected,
                "eligible_at_cutoff": len(selected) == 0 if args.mode == "freeze" else None,
            }
        )
        time.sleep(0.35)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
