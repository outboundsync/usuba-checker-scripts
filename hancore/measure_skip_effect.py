#!/usr/bin/env python3
"""Effect of the v3-fixes skip conditions (/dev/null curl, mktemp/regex-guarded vars, hyprctl eval, helper-wrapped curl, regular-file readline, vendored paths) on the USB-HC rules.
Re-runs hancore_rules_v2.check (all rules, per_file=50) over the Dell-key-free pool, compares per rule (DESIGN split, then test) with the cached hits of the previous rule code
(checker-rules/hits.jsonl + hits_model.jsonl, ids mapped H->HC), using measure_v3.per_rule (file-level lower-bound precision, false-hit on works plugins).
Writes <out>/hits_hc_after.jsonl and <out>/skip_effect.json; never touches checker-rules/. usage: python3 hancore/measure_skip_effect.py [--out DIR]"""
import sys, os, json, argparse, collections
H = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(H)
sys.path[:0] = [os.path.join(ROOT, "functest/usuba"), os.path.join(ROOT, "functest"), H]
import hancore_rules_v2 as V, measure_v3 as M
from rules_v2_pool import read_tree
def _one(r):
    import signal
    def h(*a): raise TimeoutError()
    signal.signal(signal.SIGALRM, h); signal.alarm(60)
    try: hits = [dict(rule=x["rule"], file=x["file"], line=x["line"]) for x in V.check(read_tree(r["src"]), enabled=set(V.RULES), per_file=50)]
    except Exception: hits = []
    finally: signal.alarm(0)
    return r["repo"], hits
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default="/workspace/usuba-runs/v3-fixes"); a = ap.parse_args()
    pool, F, before = M.load(None)
    from multiprocessing import Pool
    with Pool(8) as P: res = P.map(_one, list(pool.values()), chunksize=20)
    after = {repo: h for repo, h in res}
    with open(a.out + "/hits_hc_after.jsonl", "w") as f:
        for repo, h in res: f.write(json.dumps(dict(repo=repo, hits=h)) + "\n")
    reg = {k: v[0] for k, v in V.RULES.items()}; out = {}
    for split in ("design", "test"):
        rows = [r for r in pool.values() if r["split"] == split]; out[split] = {}
        for k, cat in sorted(reg.items()):
            b = M.per_rule(rows, F, before, k, cat); n = M.per_rule(rows, F, after, k, cat)
            keep = ("fired_reviewed", "plugin_file_precision_strict", "plugin_file_precision_lower", "hitfiles", "hitfile_precision_strict", "false_hit", "lift")
            out[split][k] = dict(before={x: b[x] for x in keep}, after={x: n[x] for x in keep})
    json.dump(out, open(a.out + "/skip_effect.json", "w"), indent=1)
    for k, v in out["design"].items():
        if v["before"]["hitfiles"] != v["after"]["hitfiles"]: print(k, "hitfiles", v["before"]["hitfiles"], "->", v["after"]["hitfiles"], "strict", v["before"]["plugin_file_precision_strict"], "->", v["after"]["plugin_file_precision_strict"], "FH", v["before"]["false_hit"], "->", v["after"]["false_hit"])
if __name__ == "__main__": main()
