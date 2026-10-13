"""Usuba Checker calibration against runs/harvest/SPOTCHECK.md (hand-labelled real/fake rows)."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from usuba import checks
import rescore
PIN = {465: 1, 503: 0, 392: 1, 441: 2, 593: 3, 549: 2, 497: 3}
idx = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "/tmp/hv/index.json"))
pick = {}
for r in idx:
    if r["i"] in PIN:
        if r["sample"] == PIN[r["i"]]: pick[r["i"]] = r
    elif r["in_verified"]: pick.setdefault(r["i"], r)
def files_of(d):
    out = {}
    for root, _, fs in os.walk(d):
        for f in fs:
            p = os.path.join(root, f)
            try: out[os.path.relpath(p, d)] = open(p, errors="replace").read()
            except Exception: pass
    return out
res = []; ok = 0
for i, r in sorted(pick.items()):
    fl = files_of(r["dir"])
    out = open(r["dir"] + ".out", errors="replace").read() if os.path.exists(r["dir"] + ".out") else ""
    rs = [checks.fmt(f) for f in checks.check(fl) if checks.blocking(f)]
    h = {"task": r["task"], "messages": [{}, {"content": ""}]}
    rs += [x[1] for x in rescore.task_findings(h, fl, out)]
    fail = bool(rs)
    good = fail == (r["label"] == "fake")
    ok += good
    res.append({"i": i, "sample": r["sample"], "label": r["label"], "fail": fail, "match": good, "reasons": rs[:3]})
    print(f"{'OK ' if good else 'XX '} {i}_s{r['sample']} {r['label']:4} {'FAIL' if fail else 'pass'}  {(rs[0] if rs else '')[:150]}")
print(f"{ok}/{len(res)} match")
json.dump(res, open(os.path.join(os.path.dirname(__file__), "calib_harvest.json"), "w"), indent=1)
