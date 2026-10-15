#!/usr/bin/env python3
"""Parse raw model candidates -> validated specs (cands.json), run on the DESIGN split only, report per-candidate design metrics.
Usage: measure_cands_v3.py parse | run | report"""
import sys, os, json, re, glob, collections, signal
H = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(H)
sys.path[:0] = [os.path.join(ROOT, "functest/usuba"), H]
OUT = "/workspace/usuba-runs/checker-rules"
import hancore_rules_model as MR
CATS = ["secrets-credentials", "file-safety-symlink-perms", "url-scheme-network", "remote-code-pinning", "rich-text-markup-injection", "shell-lua-injection", "process-lifecycle-timeouts"]
def parse():
    cands = []; rej = collections.Counter()
    for f in sorted(glob.glob(OUT + "/cands_raw/*.json")):
        d = json.load(open(f)); t = d["content"].strip()
        t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
        try: arr = json.loads(t)
        except Exception:
            m = re.search(r"\[.*\]", t, re.S)
            try: arr = json.loads(m.group(0))
            except Exception: rej["unparseable_response"] += 1; continue
        for s in arr:
            if not isinstance(s, dict): continue
            s["category"] = d["cat"]; s["src"] = os.path.basename(f)
            s["file_types"] = [x for x in s.get("file_types", []) if x in MR.EXTS]
            if not s["file_types"]: rej["no_code_file_type"] += 1; continue
            try: MR.compile_spec(s)
            except Exception as e: rej[str(e)[:30]] += 1; continue
            cands.append(s)
    # dedupe on (cat, regex, exclude, file conds)
    seen = {}; out = []
    for s in cands:
        k = (s["category"], s["line_regex"], s.get("line_exclude_regex"), s.get("file_must_contain_regex"), s.get("file_must_not_contain_regex"), s.get("window_must_not_contain_regex"), tuple(s["file_types"]))
        if k in seen: rej["duplicate"] += 1; continue
        seen[k] = 1; out.append(s)
    for i, s in enumerate(out): s["cid"] = f"C{i:03d}"
    json.dump(out, open(OUT + "/cands.json", "w"), indent=1)
    print("candidates", len(out), "rejected", dict(rej), collections.Counter(s["category"] for s in out))
def _one(r):
    from rules_v2_pool import read_tree
    def h(*a): raise TimeoutError()
    signal.signal(signal.SIGALRM, h); signal.alarm(120)
    try: hits = MR.check_model(read_tree(r["src"]), RULES, per_file=50)
    except Exception: hits = []
    finally: signal.alarm(0)
    return r["repo"], hits
RULES = {}
def run(split, ids_file, out_file):
    global RULES
    specs = json.load(open(ids_file))
    RULES = {s.get("cid") or s["id"]: MR.compile_spec(s) for s in specs}
    for s in specs: RULES[s.get("cid") or s["id"]]["summary"] = s.get("summary", "")
    pool = json.load(open(OUT + "/pool.json")); items = [r for r in pool.values() if r["split"] == split]
    sys.path.insert(0, H)
    from multiprocessing import Pool
    with Pool(6) as P: res = P.map(_one, items, chunksize=20)
    with open(out_file, "w") as f:
        for repo, hits in res: f.write(json.dumps(dict(repo=repo, hits=hits)) + "\n")
    print("ran", len(items), "plugins", sum(len(h) for _, h in res), "hits")
def report(split="design", hits_file=None):
    import measure_v3 as M
    pool = json.load(open(OUT + "/pool.json")); F = json.load(open(OUT + "/findings.json")); specs = json.load(open(OUT + "/cands.json"))
    hits = {}
    for l in open(hits_file or OUT + "/hits_cands_design.jsonl"):
        d = json.loads(l); hits[d["repo"]] = d["hits"]
    rows = [r for r in pool.values() if r["split"] == split]; res = {}
    for s in specs:
        res[s["cid"]] = M.per_rule(rows, F, hits, s["cid"], s["category"]); res[s["cid"]].update(name=s.get("name"), category=s["category"])
    json.dump(res, open(OUT + "/cands_design_metrics.json", "w"), indent=1)
    return res
if __name__ == "__main__":
    c = sys.argv[1]
    if c == "parse": parse()
    elif c == "run": run("design", OUT + "/cands.json", OUT + "/hits_cands_design.jsonl")
    elif c == "report":
        res = report()
        for k, v in sorted(res.items(), key=lambda x: (x[1]["category"], -(x[1]["lift"] or 0))):
            print(k, v["category"][:14], (v["name"] or "")[:40].ljust(40), "fired", v["fired_reviewed"], "P", v["plugin_precision"], "lift", v["lift"], "FH", v["false_hit"], "Pfile", v["plugin_file_precision_strict"], "Rfile", v["recall_file"])
