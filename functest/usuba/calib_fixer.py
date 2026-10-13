#!/usr/bin/env python3
"""Calibrate the Usuba Checker on the runs/fixer grader-passes that were hand-checked (runs/fixer/README.md).
Every answer the old grader passed is re-scored; rejected ones must now fail, kept ones must pass."""
import json, os, sys
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__)); FT = os.path.dirname(HERE); ROOT = os.path.dirname(FT)
sys.path.insert(0, FT); import rescore
# hand-check verdicts (README.md): keep = accepted (firm or lenient), reject = rejected; doubtful hand2/10 counted as reject
# (its night-light button runs `hyprsunset enable/disable`, which is an invented CLI and is named in the hardening brief)
LABELS = {"base": {51: "keep", 52: "keep", 53: "keep", 54: "keep", 0: "reject", 1: "reject", 2: "reject", 5: "reject", 7: "reject",
                   19: "reject", 31: "reject", 45: "reject", 48: "reject"},
          "hand": {51: "keep", 52: "keep", 54: "keep", 27: "reject", 49: "reject"},
          "hand2": {51: "keep", 52: "keep", 54: "keep", 13: "keep", 31: "keep", 18: "keep", 2: "keep", 10: "reject", 50: "reject",
                    49: "reject", 30: "reject", 0: "reject", 16: "reject"}}
items = []
for v, lab in LABELS.items():
    for l in open(os.path.join(ROOT, "runs/fixer", v, "rows.jsonl")):
        r = json.loads(l)
        if r["first_pass_round"] is None: continue
        g = r["rounds"][r["first_pass_round"]]
        items.append((v, r["i"], lab.get(r["i"], "unlabelled"), {"output": g["output"], "finish": g["finish"]}))
def one(it):
    v, i, lab, g = it
    s = rescore.score_row(i, rescore.hold[i], g)
    return dict(variant=v, i=i, task=s["task"], label=lab, now_pass=s["pass_"], ok=(s["pass_"] == (lab == "keep")),
                reasons=(s.get("static_fails") or []) + (s.get("runtime_errors") or []))
with ThreadPoolExecutor(int(os.environ.get("J", "4"))) as ex: res = list(ex.map(one, items))
for r in res:
    print(("OK  " if r["ok"] else "BAD ") + f"{r['variant']:5} {r['i']:2} {r['task']:28} label={r['label']:6} now={'PASS' if r['now_pass'] else 'FAIL'}",
          "|", (r["reasons"][0][:200] if r["reasons"] else ""))
print(f"agreement {sum(r['ok'] for r in res)}/{len(res)}; rejected now failing {sum(not r['now_pass'] for r in res if r['label']=='reject')}/{sum(r['label']=='reject' for r in res)}; kept now passing {sum(r['now_pass'] for r in res if r['label']=='keep')}/{sum(r['label']=='keep' for r in res)}")
json.dump(res, open(os.path.join(HERE, "calib_fixer.json"), "w"), indent=1)
