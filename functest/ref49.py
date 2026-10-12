#!/usr/bin/env python3
"""Score the 49 clean-holdout REFERENCE (gold) answers with the current functest; compare with the previous functest's rows."""
import json, os, sys, collections
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); sys.path.insert(0, HERE)
import rescore
clean = [json.loads(l) for l in open(os.path.join(ROOT, "clean/holdout_clean.jsonl"))]
old = json.load(open(os.path.join(HERE, "results.json")))["rows"]["REFERENCE"]
if __name__ == "__main__":
    items = [(c["holdout_i"], rescore.hold[c["holdout_i"]], {"output": c["messages"][2]["content"], "finish": "stop"}) for c in clean]
    with ThreadPoolExecutor(int(os.environ.get("J", "4"))) as ex:
        rows = list(ex.map(lambda a: rescore.score_row(*a), items))
    out = []
    for (i, h, _), r in zip(items, rows):
        o = old[i]; out.append(dict(holdout_i=i, task=h["task"], old=o["pass_"], new=r["pass_"], categories=r["categories"],
                                    static_fails=r.get("static_fails"), runtime_errors=r.get("runtime_errors")))
        if o["pass_"] != r["pass_"]: print("FLIP", i, h["task"], o["pass_"], "->", r["pass_"], r["categories"], (r.get("runtime_errors") or r.get("static_fails") or [])[:2], flush=True)
    s = {"old": f"{sum(x['old'] for x in out)}/49", "new": f"{sum(x['new'] for x in out)}/49",
         "per_task_new": {t: f"{sum(x['new'] for x in out if x['task'].split(':')[0]==t)}/{sum(1 for x in out if x['task'].split(':')[0]==t)}" for t in sorted({x['task'].split(':')[0] for x in out})}}
    print(json.dumps(s)); json.dump({"summary": s, "rows": out}, open(os.path.join(HERE, "ref49_results.json"), "w"), indent=1)
