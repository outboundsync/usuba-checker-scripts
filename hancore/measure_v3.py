#!/usr/bin/env python3
"""Measurement v3: file-level matching, finding-level recall per bug kind / category, file-level lower-bound precision.
Usage: measure_v3.py [--split design|test|all] [--rulesets old_enabled,new_enabled,...] ; writes metrics_v3_<split>.json
Definitions (findings = HANCORE strong/likely category findings at the reviewed commit, clean-review prose excluded; split by repo hash):
 finding recalled (file-level): finding names >=1 file in its prose AND some hit of a rule in the set lands in one of those files (same plugin).
 finding recalled (plugin-level): any hit of the set in that plugin (used for findings whose prose names no file).
 recall_file = recalled_file / findings with parsed files; recall_blend = (file-level for parsed, plugin-level for unparsed) / all findings.
 hit-file precision: a hit file in a reviewed plugin is TP if HANCORE named that file in a same-category finding; FP if the plugin has no same-category finding
   or only findings that name other files; INDETERMINATE if its same-category findings name no file (excluded from strict, counted TP in upper, FP in lower).
 plugin-file precision: same, per fired plugin (TP if any hit file is named)."""
import sys, os, json, collections, argparse
H = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(H)
sys.path[:0] = [os.path.join(ROOT, "functest/usuba"), H]
OUT = "/workspace/usuba-runs/checker-rules"
def fmatch(hf, cf): return hf == cf or hf.endswith("/" + cf) or cf.endswith("/" + hf) or os.path.basename(hf) == os.path.basename(cf)
def load(rule_cat):
    pool = json.load(open(OUT + "/pool.json")); F = json.load(open(OUT + "/findings.json")); hits = {}
    for fn in ("hits.jsonl", "hits_model.jsonl"):
        if os.path.exists(OUT + "/" + fn):
            for l in open(OUT + "/" + fn):
                d = json.loads(l); hits.setdefault(d["repo"], []).extend(d["hits"])
    return pool, F, hits
def stat(rows, F, hits, cat, rules, excl_clean=True):
    """returns dict of finding-level and hit-level counts for category cat and rule set."""
    rs = set(rules); out = collections.Counter(); kinds = collections.defaultdict(collections.Counter)
    rev = [r for r in rows if r["reviewed"]]
    for r in rev:
        hs = [h for h in hits.get(r["repo"], []) if h["rule"] in rs]
        fl = [f for f in F.get(r["repo"], []) if f["cat"] == cat and not (excl_clean and f["clean"])]
        cited = [set(f["files"]) for f in fl if f["files"]]
        allc = set().union(*cited) if cited else set()
        for f in fl:
            rec_p = bool(hs); parsed = bool(f["files"]); rec_f = parsed and any(fmatch(h["file"], c) for h in hs for c in f["files"])
            o = ["findings"]; out["findings"] += 1
            if parsed: out["findings_parsed"] += 1; out["rec_file"] += rec_f
            out["rec_plugin"] += rec_p; out["rec_blend"] += (rec_f if parsed else rec_p)
            for k in f["kinds"]:
                kk = kinds[k]; kk["n"] += 1; kk["n_parsed"] += parsed; kk["rec_file"] += rec_f; kk["rec_plugin"] += rec_p; kk["rec_blend"] += (rec_f if parsed else rec_p)
        # hit-level
        hf = {h["file"] for h in hs}
        for f_ in hf:
            if not fl: st = "fp"
            elif not allc: st = "ind"
            else: st = "tp" if any(fmatch(f_, c) for c in allc) else "fp"
            out["hf_" + st] += 1
        if hs:
            out["fired"] += 1
            if not fl: out["pl_fp"] += 1
            elif not allc: out["pl_ind"] += 1
            else: out["pl_tp" if any(fmatch(h["file"], c) for h in hs for c in allc) else "pl_fp"] += 1
            if fl: out["fired_pos_nc"] += 1
        if fl: out["pos_plugins"] += 1
    return out, kinds
def ratio(a, b): return round(a / b, 3) if b else None
def summarize(o):
    s = dict(findings=o["findings"], findings_parsed=o["findings_parsed"], recall_file=ratio(o["rec_file"], o["findings_parsed"]), recall_plugin=ratio(o["rec_plugin"], o["findings"]), recall_blend=ratio(o["rec_blend"], o["findings"]),
             fired_plugins=o["fired"], plugin_precision_nc=ratio(o["fired_pos_nc"], o["fired"]),
             plugin_file_precision_strict=ratio(o["pl_tp"], o["pl_tp"] + o["pl_fp"]), plugin_file_precision_lower=ratio(o["pl_tp"], o["fired"]), plugin_file_precision_upper=ratio(o["pl_tp"] + o["pl_ind"], o["fired"]),
             hitfile_precision_strict=ratio(o["hf_tp"], o["hf_tp"] + o["hf_fp"]), hitfiles=o["hf_tp"] + o["hf_fp"] + o["hf_ind"], hitfiles_indeterminate=o["hf_ind"], hitfiles_tp=o["hf_tp"])
    return s
def false_hit(rows, hits, cat, rules, cats_any_nc):
    rs = set(rules); neg = [r for r in rows if r["label"] == "works" and cat not in cats_any_nc.get(r["repo"], set())]
    f = sum(any(h["rule"] in rs for h in hits.get(r["repo"], [])) for r in neg)
    return ratio(f, len(neg)), f, len(neg)
def per_rule(rows, F, hits, rule, cat):
    """old-style plugin-level row (positives = non-clean strong/likely finding in cat) + file-level."""
    rev = [r for r in rows if r["reviewed"]]
    pos = {r["repo"] for r in rev if any(f["cat"] == cat and not f["clean"] for f in F.get(r["repo"], []))}
    fired = {r["repo"] for r in rows if any(h["rule"] == rule for h in hits.get(r["repo"], []))}
    nf = len([r for r in rev if r["repo"] in fired]); tp = len([1 for r in rev if r["repo"] in fired and r["repo"] in pos])
    prec = tp / nf if nf else None; base = len(pos) / len(rev) if rev else None
    any_nc = {r["repo"]: {f["cat"] for f in F.get(r["repo"], [])} for r in rows}
    fh = false_hit(rows, hits, cat, [rule], any_nc)
    o, k = stat(rows, F, hits, cat, [rule])
    s = summarize(o)
    s.update(plugin_precision=prec and round(prec, 3), base_rate=base and round(base, 3), lift=round(prec / base, 2) if prec and base else None, false_hit=fh[0], false_hit_n=fh[1], works_neg=fh[2], fired_reviewed=nf, tp=tp)
    return s
def cat_summary(rows, F, hits, cat, rules):
    o, k = stat(rows, F, hits, cat, rules); s = summarize(o)
    any_nc = {r["repo"]: {f["cat"] for f in F.get(r["repo"], [])} for r in rows}
    s["false_hit"] = false_hit(rows, hits, cat, rules, any_nc)[0]; s["rules"] = sorted(rules)
    s["kinds"] = {kn: dict(n=v["n"], n_parsed=v["n_parsed"], recall_file=ratio(v["rec_file"], v["n_parsed"]), recall_plugin=ratio(v["rec_plugin"], v["n"]), recall_blend=ratio(v["rec_blend"], v["n"])) for kn, v in sorted(k.items(), key=lambda x: -x[1]["n"])}
    return s
def rule_registry():
    import hancore_rules_v2 as V
    reg = {k: v[0] for k, v in V.RULES.items()}
    return reg, V
def rulesets(reg):
    en = json.load(open(ROOT + "/functest/usuba/rules_v2_enabled.json"))
    old_en = set(en["enabled"]); sets = {"old_enabled": old_en, "old_all": {k for k in reg if int(k[-2:]) <= 18}}
    mf = ROOT + "/functest/usuba/model_rules_v3.json"
    if os.path.exists(mf):
        mr = json.load(open(mf)); sets["new_enabled"] = old_en | set(mr.get("enabled", [])); sets["model_only_enabled"] = set(mr.get("enabled", []))
    return sets
def compute(split, rule_cat, sets, extra_rules=None):
    pool, F, hits = load(rule_cat)
    rows = [r for r in pool.values() if split == "all" or r["split"] == split]
    cats = sorted({c for c in rule_cat.values()}); res = dict(split=split, n_plugins=len(rows), n_reviewed=sum(r["reviewed"] for r in rows), rules={}, sets={})
    for k, c in rule_cat.items():
        if any(k in v for v in sets.values()) or (extra_rules and k in extra_rules): res["rules"][k] = per_rule(rows, F, hits, k, c)
    for sn, rs in sets.items():
        res["sets"][sn] = {c: cat_summary(rows, F, hits, c, {k for k in rs if rule_cat[k] == c}) for c in cats if any(rule_cat[k] == c for k in rs)}
        # categories with no enabled rule: zero hits
        for c in cats:
            if c not in res["sets"][sn]: res["sets"][sn][c] = cat_summary(rows, F, hits, c, set())
    return res
if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--split", default="design"); ap.add_argument("--extra", default="")
    a = ap.parse_args()
    reg, V = rule_registry(); sets = rulesets(reg)
    res = compute(a.split, reg, sets, set(a.extra.split(",")) if a.extra else None)
    json.dump(res, open(OUT + f"/metrics_v3_{a.split}.json", "w"), indent=1)
    print("split", a.split, res["n_plugins"], res["n_reviewed"])
    for sn, d in res["sets"].items():
        print("==", sn)
        for c, s in d.items(): print(c[:26].ljust(26), "n=%s parsed=%s Rfile=%s Rplug=%s Rblend=%s Pnc=%s Pfile(strict/low/up)=%s/%s/%s FH=%s" % (s["findings"], s["findings_parsed"], s["recall_file"], s["recall_plugin"], s["recall_blend"], s["plugin_precision_nc"], s["plugin_file_precision_strict"], s["plugin_file_precision_lower"], s["plugin_file_precision_upper"], s["false_hit"]))
