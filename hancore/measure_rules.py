#!/usr/bin/env python3
"""Plugin-level precision/recall of USB-W rules against HANCORE findings at the reviewed commit (NON-holdout plugins only).
Positive for a rule = HANCORE raised a finding in the mapped category at that commit. Precision is a lower bound:
HANCORE does not always mention every instance, and its category tags are regex-derived."""
import sys, os, json, collections
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H); sys.path.insert(0, os.path.join(H, "../functest"))
import common, fetch
from usuba import hancore_rules as HR
MAP = {"USB-W01": "install-deps-packaging", "USB-W02": "secrets-credentials", "USB-W03": "remote-code-pinning", "USB-W04": "file-safety-symlink-perms",
       "USB-W05": "privileged-system", "USB-W06": "rich-text-markup-injection", "USB-W07": "shell-lua-injection", "USB-W08": "process-lifecycle-timeouts",
       "USB-W09": "url-scheme-network", "USB-W10": "unbounded-input-resource"}
HOLD = set(open(os.path.join(H, "../eval/hancore_holdout/plugin_ids.txt")).read().split())
d = common.load(); rows = []
for p, v in d.items():
    if p in HOLD or not v["sha"] or not v["gt"]: continue
    src = os.path.join(fetch.CACHE, common.repo_of(p).replace("/", "__") + "@" + v["sha"])
    if not os.path.exists(src + "/.ok"): continue
    files = fetch.read_files(src)
    if not files: continue
    fired = {f["rule"] for f in HR.check(files, experimental=True)}
    cats = {c for x in v["gt"] for c in x["categories"]}
    rows.append((p, fired, cats))
res = {}
for r, cat in MAP.items():
    tp = sum(1 for _, f, c in rows if r in f and cat in c); fp = sum(1 for _, f, c in rows if r in f and cat not in c)
    fn = sum(1 for _, f, c in rows if r not in f and cat in c); base = (tp + fn) / len(rows)
    prec = tp / (tp + fp) if tp + fp else 0; rec = tp / (tp + fn) if tp + fn else 0
    on = prec >= 0.5 and prec >= base + 0.10
    if r in ("USB-W02",): on = True   # maintainer override: committed keys always warn
    res[r] = dict(category=cat, tp=tp, fp=fp, fn=fn, precision=round(prec, 3), recall=round(rec, 3), base_rate=round(base, 3), lift=round(prec / base, 2) if base else None, default="on" if on else "experimental")
print("plugins", len(rows))
for r, x in res.items(): print(r, x)
json.dump(dict(plugins=len(rows), rule_criterion="on if precision>=0.5 and precision>=base_rate+0.10", rules=res), open(os.path.join(H, "rule_metrics.json"), "w"), indent=1)
