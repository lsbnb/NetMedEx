"""Run semantic edge extraction through the OpenAI Batch API (half price).

Used by ``netmedex network --edge_method semantic --batch_dir DIR``. The graph
is built by the normal pipeline; only SemanticRelationshipExtractor._call_llm
is replaced while it runs:

- a prompt whose answer is already in DIR/responses.jsonl is answered from it;
- any other prompt is queued as a Batch request and that article is skipped.

Queued requests are submitted when the build finishes and the command exits,
saying to run it again later. The next run collects finished batches and
rebuilds; the extractor's second-pass prompts (compact retry / coverage) depend
on first-pass answers, so a full build takes two or three runs. When no prompt
is left unanswered the graph is saved as usual. ``--batch_wait`` does all of
this in one run, polling until the batches finish (they complete within 24 h,
usually much sooner).

Answers are keyed by a hash of the prompt, so prompts must be identical across
runs -- which is why entity selection breaks ties deterministically
(pubtator_graph_data.NonMeshNodeCollection).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

REQUESTS_PER_BATCH = 10_000  # under the API's 50k requests / 200 MB per batch


def request_key(prompt: str, max_tokens: int, response_format: dict | None) -> str:
    payload = json.dumps([prompt, max_tokens, response_format], sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


class _Queued(Exception):
    """Raised for an unanswered prompt; the extractor records it as an API error
    for that article and does not cache it, so the article is redone next run."""


class _DropQueued(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "queued for the Batch API" not in record.getMessage()


class BatchRun:
    def __init__(self, workdir: str | Path, model: str, client):
        self.dir = Path(workdir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.model = model
        self.client = client  # openai.OpenAI
        self.responses = self._load_responses()
        self.pending: dict[str, dict] = {}
        self.replayed = 0
        self._lock = threading.Lock()

    # --- request bodies ---------------------------------------------------------

    def _body(self, system: str, prompt: str, max_tokens: int, response_format) -> dict:
        """Same parameters as LLMClient.chat_completion_text sends for OpenAI."""
        body = {"model": self.model,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": prompt}],
                "max_completion_tokens": max_tokens}
        if self.model.lower().startswith("gpt-5"):
            effort = os.getenv("NETMEDEX_REASONING_EFFORT", "").strip().lower()
            if effort:
                body["reasoning_effort"] = effort
        else:
            body["temperature"] = 0.1
        if response_format:
            body["response_format"] = response_format
        return body

    # --- record / replay ------------------------------------------------------------

    @contextmanager
    def patched_extractor(self):
        from netmedex.semantic_re import SEMANTIC_SYSTEM_PROMPT, SemanticRelationshipExtractor

        original = SemanticRelationshipExtractor._call_llm
        run = self

        def call_llm(_self, prompt, max_tokens=1500, response_format=None, pmid="",
                     current=0, total=0, client=None):
            key = request_key(prompt, max_tokens, response_format)
            with run._lock:
                if key in run.responses:
                    run.replayed += 1
                    return run.responses[key]
                run.pending.setdefault(key, {
                    "custom_id": key, "method": "POST", "url": "/v1/chat/completions",
                    "body": run._body(SEMANTIC_SYSTEM_PROMPT, prompt, max_tokens, response_format),
                })
            raise _Queued(f"queued for the Batch API: PMID {pmid}")

        # The extractor logs each failed call as an error; a queued prompt is
        # expected here, so keep those lines out of the log (real errors still show).
        sem_logger = logging.getLogger("netmedex.semantic_re")
        quiet = _DropQueued()
        sem_logger.addFilter(quiet)
        SemanticRelationshipExtractor._call_llm = call_llm
        try:
            yield
        finally:
            SemanticRelationshipExtractor._call_llm = original
            sem_logger.removeFilter(quiet)

    # --- persistence -----------------------------------------------------------------

    def _load_responses(self) -> dict[str, str]:
        out = {}
        path = self.dir / "responses.jsonl"
        if path.exists():
            for line in path.read_text().splitlines():
                rec = json.loads(line)
                out[rec["custom_id"]] = rec["content"]
        return out

    def _batches(self) -> list[dict]:
        path = self.dir / "batches.json"
        return json.loads(path.read_text()) if path.exists() else []

    def _save_batches(self, batches: list[dict]) -> None:
        (self.dir / "batches.json").write_text(json.dumps(batches, indent=1))

    def in_flight(self) -> int:
        return sum(1 for b in self._batches() if not b.get("collected"))

    # --- submit / collect ---------------------------------------------------------------

    def submit(self) -> int:
        """Submit queued requests not already in an open batch; returns how many."""
        open_ids = {cid for b in self._batches() if not b.get("collected") for cid in b["custom_ids"]}
        lines = [json.dumps(r, ensure_ascii=False) for k, r in self.pending.items()
                 if k not in open_ids]
        batches = self._batches()
        for i in range(0, len(lines), REQUESTS_PER_BATCH):
            chunk = lines[i:i + REQUESTS_PER_BATCH]
            path = self.dir / f"requests_{len(batches):03d}.jsonl"
            path.write_text("\n".join(chunk) + "\n")
            with path.open("rb") as f:
                uploaded = self.client.files.create(file=f, purpose="batch")
            batch = self.client.batches.create(input_file_id=uploaded.id,
                                               endpoint="/v1/chat/completions",
                                               completion_window="24h")
            batches.append({"id": batch.id, "requests": len(chunk), "collected": False,
                            "custom_ids": [json.loads(x)["custom_id"] for x in chunk]})
            self._save_batches(batches)
            logger.info(f"Submitted batch {batch.id} ({len(chunk)} requests)")
        return len(lines)

    def collect(self, wait: bool = False, poll_seconds: int = 60) -> int:
        """Store answers of finished batches; with `wait`, until none is open.
        Failed requests are not stored, so they are queued again next build."""
        stored = 0
        while True:
            batches, open_count = self._batches(), 0
            for b in batches:
                if b.get("collected"):
                    continue
                batch = self.client.batches.retrieve(b["id"])
                if batch.status in ("validating", "in_progress", "finalizing", "cancelling"):
                    open_count += 1
                    continue
                if batch.output_file_id:
                    text = self.client.files.content(batch.output_file_id).text
                    with (self.dir / "responses.jsonl").open("a") as out:
                        for line in text.splitlines():
                            rec = json.loads(line)
                            body = (rec.get("response") or {}).get("body") or {}
                            choices = body.get("choices") or []
                            if (rec.get("response") or {}).get("status_code") != 200 or not choices:
                                continue
                            content = choices[0]["message"].get("content") or ""
                            out.write(json.dumps({"custom_id": rec["custom_id"],
                                                  "content": content}, ensure_ascii=False) + "\n")
                            self.responses[rec["custom_id"]] = content
                            stored += 1
                b["collected"], b["status"] = True, batch.status
                self._save_batches(batches)
                logger.info(f"Collected batch {b['id']} ({batch.status})")
            if not (wait and open_count):
                return stored
            logger.info(f"{open_count} batch(es) still running; checking again in {poll_seconds}s")
            time.sleep(poll_seconds)
