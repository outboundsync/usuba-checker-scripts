#!/usr/bin/env python3
"""Panel items for the scope-v4 sets: S1 warn-level candidates (drafts/S1_candidates_unlabelled.jsonl) and S3 added findings (b0 rows of dell/holdout/s4).
Context is a +-12 line window of the cited file. Eval-only; items are PROVISIONAL inputs for tools/judge_panel.py.
usage: FT_OMARCHY=... python3 build_scope_items.py MODELS_DIR SCOPE_DIR OUT.jsonl"""
import json
import os
import sys

models, scope, out = sys.argv[1:4]
sys.path.insert(0, models)
from scope import checker_findings as CF  # noqa: E402
from scope import run_b0  # noqa: E402

D = os.path.join(scope, "drafts")


def window(files, fname, line, n=12):
    t = files.get(fname)
    if t is None:
        cand = [k for k in files if k.endswith("/" + fname) or os.path.basename(k) == os.path.basename(fname)]
        t = files.get(cand[0]) if cand else None
    if t is None:
        return ""
    ls = t.split("\n")
    a = max(0, int(line or 1) - 1 - n)
    return "\n".join("%d: %s" % (i + 1, ls[i]) for i in range(a, min(len(ls), a + 2 * n + 1)))[:7000]


plugins = {}
for name in ("dell", "s4", "holdout"):
    for r in run_b0.load_set(name, 0):
        plugins[(name, r["plugin"])] = r
by_plugin = {}
for (_, p), r in plugins.items():
    by_plugin.setdefault(p, r)
items = []
for line in open(os.path.join(D, "S1_candidates_unlabelled.jsonl")):
    c = json.loads(line)
    plug, rule, fname, idx = c["key"].split("|")
    r = by_plugin.get(plug)
    if not r:
        continue
    fs = [f for f in CF.findings_for(r["files"]) if f["rule"] == rule and f["file"] == fname]
    f = fs[min(int(idx), len(fs) - 1)] if fs else None
    if not f:
        continue
    items.append(dict(id="s1w:" + c["key"], kind="S1", plugin=plug, rule=rule, claim="Checker warn-level finding: " + f["message"], file=fname, line=f["line"],
                      context=window(r["files"], fname, f["line"]), evidence="plugin runs on real hardware (Dell sweep: works)"))
n1 = len(items)
for name in ("dell", "s4", "holdout"):
    for line in open(os.path.join(scope, "b0", "b0-%s.rows.jsonl" % name)):
        row = json.loads(line)
        if not row.get("out"):
            continue
        r = plugins[(name, row["plugin"])]
        for k, a in enumerate(row["out"]["added_findings"]):
            items.append(dict(id="s3:%s:%s:%d" % (name, row["plugin"], k), kind="S3", plugin=row["plugin"], rule=a["category"],
                              claim=a["finding"], file=a["file"], line=a["line"], context=window(r["files"], a["file"], a["line"]),
                              evidence="drafted by the stock 9B baseline; quoted line: " + a["quote"][:300], set=name))
with open(out, "w") as w:
    for i in items:
        w.write(json.dumps(i) + "\n")
print("S1 warn items", n1, "S3 items", len(items) - n1)
