#!/usr/bin/env python3
"""Create a generic SHA-256 manifest for evaluation artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--status", default="frozen")
    parser.add_argument("--file", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    missing = [str(path) for path in args.file if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Cannot freeze missing files: {missing}")
    payload = {
        "benchmark": args.benchmark,
        "status": args.status,
        "human_expert_review_claimed": False,
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "files": [
            {
                "path": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "size_bytes": path.stat().st_size,
            }
            for path in args.file
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.output.with_suffix(args.output.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(args.output)
    print(f"frozen {len(args.file)} files -> {args.output}")


if __name__ == "__main__":
    main()
