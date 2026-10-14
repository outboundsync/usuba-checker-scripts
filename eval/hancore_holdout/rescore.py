#!/usr/bin/env python3
"""Re-score a saved <name>.raw.jsonl with the current category normaliser (no API calls). python3 rescore.py <name> [...]"""
import json, os, sys
H = os.path.dirname(os.path.abspath(__file__)); sys.argv_backup = sys.argv; sys.argv = [sys.argv[0], "--backend", "dry", "--name", "x"]
import run_eval as E
for name in sys.argv_backup[1:]:
    R = [json.loads(l) for l in open(os.path.join(H, "results", name + ".raw.jsonl"))]
    res = json.load(open(os.path.join(H, "results", name + ".json")))
    tp = gt = pr = 0; cat = {c: [0, 0, 0] for c in sorted(E.SCORED)}
    for r in R:
        out = E.parse(r["raw"]) if r.get("raw") else {"findings": [{"category": c} for c in r["pred"]]}
        pred = {E.norm_cat(f.get("category")) for f in (out or {}).get("findings", []) if isinstance(f, dict)} & E.SCORED
        g = set(r["gt"]); tp += len(pred & g); gt += len(g); pr += len(pred)
        for c in cat: cat[c][0] += c in g and c in pred; cat[c][1] += c in g and c not in pred; cat[c][2] += c not in g and c in pred
    res["category_recall_micro"] = round(tp / max(1, gt), 3); res["category_precision_micro"] = round(tp / max(1, pr), 3)
    res["per_category"] = {c: dict(gt=a + b, recall=round(a / (a + b), 3) if a + b else None, precision=round(a / (a + c_), 3) if a + c_ else None) for c, (a, b, c_) in cat.items()}
    json.dump(res, open(os.path.join(H, "results", name + ".json"), "w"), indent=1)
    print(name, "category recall", res["category_recall_micro"], "precision", res["category_precision_micro"])
