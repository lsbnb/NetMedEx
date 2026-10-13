from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from netmedex.batch_llm import BatchRun
from netmedex.graph import PubTatorGraphBuilder
from netmedex.pubtator_data import PubTatorAnnotation, PubTatorArticle

REPO = Path(__file__).resolve().parent.parent


def _collection():
    arts = []
    for i in range(3):
        pmid = str(100 + i)
        ann = [PubTatorAnnotation(pmid=pmid, start=0, end=4, name="NLRP3", identifier_name=None,
                                  type="Gene", mesh="114548"),
               PubTatorAnnotation(pmid=pmid, start=10, end=29, name="acute liver failure",
                                  identifier_name=None, type="Disease", mesh="MESH:D017114")]
        arts.append(PubTatorArticle(pmid=pmid, date=None, journal=None, doi=None,
                                    title="NLRP3 in acute liver failure",
                                    abstract=f"NLRP3 promotes acute liver failure (cohort {i}).",
                                    annotations=ann, relations=[]))
    return arts


class FakeOpenAI:
    """Batches finish instantly; every request is answered with `answer`."""

    def __init__(self, answer):
        self.answer, self.uploads, self.outputs = answer, {}, {}
        self.files = SimpleNamespace(create=self._upload, content=self._content)
        self.batches = SimpleNamespace(create=self._create, retrieve=self._retrieve)

    def _upload(self, file, purpose):
        fid = f"file{len(self.uploads)}"
        self.uploads[fid] = file.read().decode()
        return SimpleNamespace(id=fid)

    def _create(self, input_file_id, endpoint, completion_window):
        bid = f"batch{len(self.outputs)}"
        lines = []
        for line in self.uploads[input_file_id].splitlines():
            rec = json.loads(line)
            body = {"choices": [{"message": {"content": self.answer}}]}
            lines.append(json.dumps({"custom_id": rec["custom_id"],
                                     "response": {"status_code": 200, "body": body}}))
        self.outputs[bid] = "\n".join(lines)
        return SimpleNamespace(id=bid)

    def _retrieve(self, bid):
        return SimpleNamespace(status="completed", output_file_id=bid)

    def _content(self, fid):
        return SimpleNamespace(text=self.outputs[fid])


def test_batch_rounds_until_every_prompt_is_answered(tmp_path):
    client = SimpleNamespace(provider="openai", model="gpt-4o", client=object())
    answer = json.dumps({"relations": [{"entity1_id": "114548_Gene",
                                        "entity2_id": "MESH:D017114_Disease",
                                        "relation_type": "promotes", "confidence": 0.9,
                                        "evidence": "NLRP3 promotes acute liver failure"}]})
    run = BatchRun(tmp_path, "gpt-4o", FakeOpenAI(answer))

    def build():
        b = PubTatorGraphBuilder(node_type="all", edge_method="semantic", llm_client=client)
        for a in _collection():
            b.add_article(a)
        return b.build(edge_weight_cutoff=0)

    rounds = []
    for _ in range(4):
        run.collect()
        run.pending.clear()
        with run.patched_extractor():
            G = build()
        rounds.append(len(run.pending))
        if not run.pending:
            break
        run.submit()
    assert rounds[0] == 3 and rounds[-1] == 0          # 3 prompts queued, then all answered
    assert G.has_edge("114548_Gene", "MESH:D017114_Disease")
    assert G.edges["114548_Gene", "MESH:D017114_Disease"]["num_relations"] == 3
    requests = [json.loads(x) for f in sorted(tmp_path.glob("requests_*.jsonl"))
                for x in f.read_text().splitlines()]
    assert len({r["custom_id"] for r in requests}) == len(requests)   # nothing submitted twice


def test_extraction_prompts_do_not_depend_on_the_hash_seed():
    """Answers are replayed by prompt hash, so prompts must be identical across
    processes; a same-name / different-type tie used to be broken by set order."""
    code = (
        "import hashlib\n"
        "from netmedex.graph import PubTatorGraphBuilder\n"
        "from netmedex.pubtator_data import PubTatorAnnotation as A, PubTatorArticle\n"
        "anns = [A(pmid='1', start=0, end=3, name='Exo', identifier_name=None, type=t, mesh='-')"
        " for t in ('Chemical', 'Disease', 'Gene')]\n"
        "anns.append(A(pmid='1', start=10, end=14, name='NLRP3', identifier_name=None,"
        " type='Gene', mesh='114548'))\n"
        "art = PubTatorArticle(pmid='1', date=None, journal=None, doi=None, title='Exo NLRP3',"
        " abstract='x', annotations=anns, relations=[])\n"
        "b = PubTatorGraphBuilder(node_type='all')\n"
        "nodes = b.add_article(art, compute_edges=False)\n"
        "print(hashlib.sha256(repr(sorted(nodes)).encode() + repr(list(nodes)).encode()).hexdigest())\n"
    )
    digests = set()
    for seed in ("1", "2", "3", "4"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        out = subprocess.run([sys.executable, "-c", code], env=env, cwd=REPO,
                             capture_output=True, text=True, timeout=120)
        assert out.returncode == 0, out.stderr[-1500:]
        digests.add(out.stdout.strip().splitlines()[-1])
    assert len(digests) == 1
