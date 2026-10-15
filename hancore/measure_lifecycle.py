#!/usr/bin/env python3
"""Measure the v3-fixes rules (functest/usuba/lifecycle_rules.py) on the Dell-key-free, hancore_holdout-free pool
(/workspace/usuba-runs/checker-rules/pool.json; split = sha1(repo) 70% design / 30% test, built by hancore/rules_v2_pool.py).
Two lenses:
  load rules (N01 N02 L01 L02 L03): the pool label is the Dell *sweep* runtime label (works/broken/unsure) of a corpus plugin (not the answer key).
     precision_broken = P(label=broken | fired); false_hit = P(fired | label=works); lift = precision_broken / base broken rate.
  hardening rules (W11 W12 W13): file-level lower-bound precision vs HANCORE findings, via hancore/measure_v3.per_rule (same definitions as H19+).
Decision uses the DESIGN split only; test is reported after the decision. Output: <out>/lifecycle_metrics.json, hits_lifecycle.jsonl
usage: python3 hancore/measure_lifecycle.py [--out /workspace/usuba-runs/v3-fixes] [--pool ...]"""
import sys, os, json, argparse, collections
H = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(H)
sys.path[:0] = [os.path.join(ROOT, "functest/usuba"), os.path.join(ROOT, "functest"), H]
import lifecycle_rules as LR
import measure_v3 as M
from rules_v2_pool import read_tree
CATS = {"USB-W11": "remote-code-pinning", "USB-W12": "remote-code-pinning", "USB-W13": "privileged-system"}
VERIFIED = {"USB-N01": "shell.qml entryPointUrl(manifest,kind); PluginRegistry.entryPointUrl", "USB-N02": "services/PluginRegistry.qml validateManifest",
            "USB-L03": "Quickshell 0.3.2 offscreen Loader test: 'Required property shell was not initialized' (docs/V3_FIXES.md)"}
def decide(res):
    """enable rule iff decided on DESIGN only: (a) host-verified deterministic fact with 0 false hits on works plugins, or
    (b) load rule: design fired_labelled>=3, precision_broken>=0.5, lift>=1.5, false_hit_works<=0.05; (c) hardening rule: fired_reviewed>=20, file-level strict precision>=0.17, false-hit<=0.05."""
    d = res["design"]["rules"]; en = []; why = {}
    for k, v in d.items():
        hf = v.get("hancore_file_level")
        if k in VERIFIED and v["works"] == 0: en.append(k); why[k] = "host-verified (" + VERIFIED[k] + "); design fired %d, works-hits 0" % v["fired_all"]
        elif hf is None and v["fired_labelled"] >= 3 and (v["precision_broken"] or 0) >= 0.5 and (v["lift"] or 0) >= 1.5 and v["false_hit_works"] <= 0.05: en.append(k); why[k] = "design precision_broken %s lift %s" % (v["precision_broken"], v["lift"])
        elif hf and hf["fired_reviewed"] >= 20 and (hf["plugin_file_precision_strict"] or 0) >= 0.17 and v["false_hit_works"] <= 0.05: en.append(k); why[k] = "design file-level strict %s" % hf["plugin_file_precision_strict"]
        else: why[k] = "experimental: design fired %d, precision_broken %s, lift %s, file-level strict %s" % (v["fired_all"], v["precision_broken"], v["lift"], hf and hf["plugin_file_precision_strict"])
    return en, why
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default="/workspace/usuba-runs/v3-fixes"); ap.add_argument("--decide-only", action="store_true"); ap.add_argument("--pool", default="/workspace/usuba-runs/checker-rules/pool.json")
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
    if a.decide_only:
        res = json.load(open(a.out + "/lifecycle_metrics.json")); en, why = decide(res)
        json.dump(dict(enabled=sorted(en), experimental=sorted(set(LR.RULES) - set(en)), reasons=why, decided_on="design split only"), open(os.path.join(LR.HERE, "lifecycle_rules_enabled.json"), "w"), indent=1); print(en); return
    pool = json.load(open(a.pool)); hits = {}; allr = set(LR.RULES)
    with open(a.out + "/hits_lifecycle.jsonl", "w") as fo:
        for repo, r in pool.items():
            files = read_tree(r["src"])
            hs = [dict(rule=h["rule"], file=h["file"], line=h["line"]) for h in LR.check(files, enabled=allr)]
            hits[repo] = hs; fo.write(json.dumps(dict(repo=repo, hits=hs)) + "\n")
    F = json.load(open(M.OUT + "/findings.json")); res = {}
    for split in ("design", "test"):
        rows = [r for r in pool.values() if r["split"] == split]
        lab = [r for r in rows if r["label"] in ("works", "broken", "unsure")]
        base = sum(r["label"] == "broken" for r in lab) / len(lab)
        res[split] = dict(n=len(rows), n_labelled=len(lab), base_broken=round(base, 4), rules={})
        for k in sorted(allr):
            fired = [r for r in lab if any(h["rule"] == k for h in hits[r["repo"]])]
            fw = sum(r["label"] == "works" for r in fired); fb = sum(r["label"] == "broken" for r in fired); works = sum(r["label"] == "works" for r in lab)
            d = dict(fired_labelled=len(fired), fired_all=sum(any(h["rule"] == k for h in hits[r["repo"]]) for r in rows), broken=fb, works=fw, unsure=len(fired) - fb - fw,
                     precision_broken=round(fb / len(fired), 3) if fired else None, false_hit_works=round(fw / works, 4), lift=round(fb / len(fired) / base, 2) if fired else None)
            if k in CATS:
                pr = M.per_rule(rows, F, hits, k, CATS[k]); d["hancore_file_level"] = {x: pr[x] for x in ("fired_reviewed", "plugin_file_precision_strict", "plugin_file_precision_lower", "plugin_file_precision_upper", "hitfile_precision_strict", "hitfiles", "plugin_precision", "base_rate", "lift")}
            res[split]["rules"][k] = d
    json.dump(res, open(a.out + "/lifecycle_metrics.json", "w"), indent=1)
    en, why = decide(res); json.dump(dict(enabled=sorted(en), experimental=sorted(allr - set(en)), reasons=why, decided_on="design split only"), open(LR.os.path.join(LR.HERE, "lifecycle_rules_enabled.json"), "w"), indent=1)
    for s in res:
        print(s, res[s]["n"], "labelled", res[s]["n_labelled"], "base_broken", res[s]["base_broken"])
        for k, d in res[s]["rules"].items(): print(" ", k, {x: d[x] for x in d if x != "hancore_file_level"}, d.get("hancore_file_level", ""))
if __name__ == "__main__": main()
