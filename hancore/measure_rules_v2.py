#!/usr/bin/env python3
"""Measure USB-H rules. Usage: measure_rules_v2.py [--run] [--split design|test|all] [--out DIR]
--run re-runs the rules over the pool (pool.json from rules_v2_pool.py) and caches hits to hits.jsonl; then metrics are computed from the cache.
Definitions (plugin level):
 positive(cat)  = HANCORE raised a strong/likely finding in cat at the reviewed commit (reviewed plugins only)
 recall         = fired / positives
 precision      = fired&positive / fired, over HANCORE-reviewed plugins (lower bound: HANCORE does not tag every instance)
 base_rate      = positives / reviewed plugins;  lift = precision / base_rate
 false-hit rate = fired / (works-labeled plugins with NO HANCORE finding of cat, any strength)"""
import sys, os, json, collections, argparse
H = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(H)
sys.path[:0] = [os.path.join(ROOT, "functest/usuba")]
import hancore_rules_v2 as V
OUT = "/workspace/usuba-runs/checker-rules"
def run(pool):
    sys.path.insert(0, H); from rules_v2_pool import read_tree
    from multiprocessing import Pool
    def job(r): return r
    items = list(pool.values())
    with Pool(8) as P: res = P.map(_one, items, chunksize=20)
    with open(OUT + "/hits.jsonl", "w") as f:
        for repo, hits in res: f.write(json.dumps(dict(repo=repo, hits=hits)) + "\n")
def _one(r):
    sys.path.insert(0, H); from rules_v2_pool import read_tree
    import signal
    def h(*a): raise TimeoutError()
    signal.signal(signal.SIGALRM, h); signal.alarm(60)
    try: hits = V.check(read_tree(r["src"]), enabled=set(V.RULES), per_file=50)
    except Exception as e: hits = []
    finally: signal.alarm(0)
    return r["repo"], [dict(rule=x["rule"], file=x["file"], line=x["line"], reason=x["reason"][:120]) for x in hits]
import re
def cited():
    """repo -> category -> set of file basenames named in strong/likely HANCORE findings at the reviewed commit."""
    sys.path.insert(0, H); import common
    norm_repo = lambda s: s.lower().rstrip("/").removesuffix(".git").split("github.com/")[-1]
    out = {}
    for p, v in common.load().items():
        d = {}
        for x in v["gt"]:
            if common.strength(x["fixed"]) not in ("strong", "likely"): continue
            fs = {os.path.basename(m) for m in re.findall(r"[\w./-]+\.(?:qml|sh|py|js|mjs|lua|json|md)\b", x["text"])}
            fs |= {m for m in re.findall(r"\b(?:bin/)?([\w.-]+)(?=:\d)", x["text"])}
            for c in x["categories"]: d.setdefault(c, set()).update(fs)
        out[norm_repo(p)] = d
    return out
def metrics(pool, hits, split):
    CI = cited()
    rows = [r for r in pool.values() if split == "all" or r["split"] == split]
    res = {}
    for rule, (cat, summ) in V.RULES.items():
        rev = [r for r in rows if r["reviewed"]]
        pos = [r for r in rev if cat in r["cats_strong"]]
        fired = lambda r: any(h["rule"] == rule for h in hits.get(r["repo"], []))
        tp = sum(fired(r) for r in pos); nf = sum(fired(r) for r in rev)
        neg = [r for r in rows if r["label"] == "works" and cat not in r["cats_any"]]
        fh = sum(fired(r) for r in neg)
        prec = tp / nf if nf else None; rec = tp / len(pos) if pos else None; base = len(pos) / len(rev) if rev else None
        # file-level: does a hit land in a file that HANCORE's finding text names (same category)?
        hp = [r for r in pos if CI.get(r["repo"], {}).get(cat)]
        fm = lambda r: {h["file"].split("/")[-1] for h in hits.get(r["repo"], []) if h["rule"] == rule} & CI.get(r["repo"], {}).get(cat, set())
        tot_hits = {(r["repo"], h["file"]) for r in rev for h in hits.get(r["repo"], []) if h["rule"] == rule}
        ok_hits = {(a, b) for a, b in tot_hits if b.split("/")[-1] in CI.get(a, {}).get(cat, set())}
        file_rec = sum(1 for r in hp if fm(r)) / len(hp) if hp else None
        file_prec = len(ok_hits) / len(tot_hits) if tot_hits else None
        res[rule] = dict(file_precision=file_prec and round(file_prec, 3), file_recall=file_rec and round(file_rec, 3), cited_positives=len(hp), category=cat, summary=summ, positives=len(pos), reviewed=len(rev), fired_reviewed=nf, tp=tp, precision=prec and round(prec, 3), recall=rec and round(rec, 3),
                         base_rate=base and round(base, 3), lift=(prec / base) if prec and base else None, works_neg=len(neg), works_neg_fired=fh, false_hit_rate=round(fh / len(neg), 3) if neg else None)
        if res[rule]["lift"]: res[rule]["lift"] = round(res[rule]["lift"], 2)
    # per category union (rules in V.ENABLED_SET if given)
    return res
def cat_union(pool, hits, split, rules):
    rows = [r for r in pool.values() if split == "all" or r["split"] == split]; out = {}
    for cat in sorted({c for c, _ in V.RULES.values()}):
        rs = {k for k in rules if V.RULES[k][0] == cat}
        fired = lambda r: any(h["rule"] in rs for h in hits.get(r["repo"], []))
        rev = [r for r in rows if r["reviewed"]]; pos = [r for r in rev if cat in r["cats_strong"]]
        neg = [r for r in rows if r["label"] == "works" and cat not in r["cats_any"]]
        tp = sum(fired(r) for r in pos); nf = sum(fired(r) for r in rev); fh = sum(fired(r) for r in neg)
        out[cat] = dict(rules=sorted(rs), positives=len(pos), plugins_with_fileline_finding=sum(fired(r) for r in rows), positives_with_finding=tp,
                        recall=round(tp / len(pos), 3) if pos else None, precision=round(tp / nf, 3) if nf else None, false_hit_rate=round(fh / len(neg), 3) if neg else None, works_neg=len(neg))
    return out
if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--run", action="store_true"); ap.add_argument("--split", default="design"); ap.add_argument("--rules", default="")
    a = ap.parse_args()
    pool = json.load(open(OUT + "/pool.json"))
    if a.run: run(pool)
    hits = {}
    for l in open(OUT + "/hits.jsonl"):
        d = json.loads(l); hits[d["repo"]] = d["hits"]
    m = metrics(pool, hits, a.split)
    rules = set(a.rules.split(",")) if a.rules else set(V.RULES)
    print(f"split={a.split} plugins={sum(1 for r in pool.values() if a.split=='all' or r['split']==a.split)}")
    for k, x in m.items(): print(k, x["category"][:22].ljust(22), f"pos={x['positives']} fired_rev={x['fired_reviewed']} P={x['precision']} R={x['recall']} base={x['base_rate']} lift={x['lift']} FP_file={x['file_precision']} FR_file={x['file_recall']} FH={x['false_hit_rate']} ({x['works_neg_fired']}/{x['works_neg']})")
    json.dump(m, open(OUT + f"/metrics_{a.split}.json", "w"), indent=1)
