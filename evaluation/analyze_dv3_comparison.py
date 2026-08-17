#!/usr/bin/env python3
"""Analyze routed incremental D-v3 against B and structured all-path D-v2."""

from __future__ import annotations
import argparse, csv, json
from collections import defaultdict
from pathlib import Path
from statistics import mean
try:
    from evaluation.metrics import _bootstrap_mean_ci, _sign_test_p_value
except ModuleNotFoundError:
    from metrics import _bootstrap_mean_ci, _sign_test_p_value

FIELDS=("correctness","completeness","relevance","grounding","mechanistic_coherence","research_value")
MAP={"traditional_text_rag":"B","structured_all_path_dv2":"D_v2","incremental_routed_dv3":"D_v3"}
INCREMENTAL={"PP014","PP015","PP016","PP018","PP019","PP020"}

def read(p):
    with Path(p).open(newline="",encoding="utf-8") as h:return list(csv.DictReader(h))
def comp(ds,unit):
    p,l,h=_bootstrap_mean_ci(ds)
    return {"unit":unit,"n":len(ds),"mean_diff":round(p,4),"bootstrap_95ci":[round(l,4),round(h,4)],"wins":sum(x>1e-9 for x in ds),"losses":sum(x< -1e-9 for x in ds),"ties":sum(abs(x)<=1e-9 for x in ds),"sign_test_p":round(_sign_test_p_value(ds),6)}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--ratings',type=Path,required=True);ap.add_argument('--audit',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    audit={r['question_id']:r for r in read(a.audit)}; vals=defaultdict(list); fv=defaultdict(list)
    for r in read(a.ratings):
        s=MAP[r['system']]; q=r['question_id']; vals[(q,s)].append(mean(float(r[f]) for f in FIELDS))
        for f in FIELDS:fv[(s,f)].append(float(r[f]))
    pq={k:mean(v) for k,v in vals.items()}; qids=sorted({q for q,s in pq})
    scores={s:{"mean":round(mean(pq[(q,s)] for q in qids),4),"fields":{f:round(mean(fv[(s,f)]),4) for f in FIELDS}} for s in ('B','D_v2','D_v3')}
    strata={"all":qids,"incremental_intervention":sorted(INCREMENTAL),"router_fallback":sorted(set(qids)-INCREMENTAL)};out={}
    for x,y in [('D_v3','B'),('D_v3','D_v2')]:
        out[f'{x}-{y}']={}
        for sn,ids in strata.items():out[f'{x}-{y}'][sn]=comp([pq[(q,x)]-pq[(q,y)] for q in ids],'question')
        clusters=defaultdict(list)
        for q in qids:clusters[audit[q]['source_question_id']].append(pq[(q,x)]-pq[(q,y)])
        out[f'{x}-{y}']['endpoint_cluster_level']=comp([mean(v) for v in clusters.values()],'source_endpoint_cluster')
    payload={"scores":scores,"contrasts":out,"router":{"intervention_questions":sorted(INCREMENTAL),"intervention_rate":len(INCREMENTAL)/len(qids)}}
    a.output.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n');print(json.dumps(payload,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
