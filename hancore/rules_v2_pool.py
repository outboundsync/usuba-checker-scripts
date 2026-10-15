#!/usr/bin/env python3
"""Pool + split for measuring the USB-H rules. Excludes (by repo, manifest id, near-dup tree) the 329 hancore_holdout plugins
and the Dell answer key; only ids/paths of the key are read for exclusion, never its labels. Split: sha1(repo) -> design (70%) / test (30%).
Source per plugin: reviewed-commit cache (hancore_cache) when HANCORE reviewed it, else corpus local_dir (current HEAD).
Writes /workspace/usuba-runs/checker-rules/pool.json"""
import sys, os, json, hashlib, collections
H = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(H)
sys.path[:0] = [H, os.path.join(ROOT, "train"), os.path.join(ROOT, "train/v2"), os.path.join(ROOT, "functest")]
import common, fetch
def read_tree(d):
    out = {}
    for r, ds, fs in os.walk(d):
        ds[:] = [x for x in ds if x not in (".git", "node_modules")]
        for f in fs:
            p = os.path.join(r, f)
            try:
                if os.path.islink(p) or os.path.getsize(p) > 400_000 or f in (".ok", ".fail"): continue
                out[os.path.relpath(p, d)] = open(p, encoding="utf-8", errors="strict").read()
            except Exception: pass
    return out
import build_train_set as B
import splits
OUT = "/workspace/usuba-runs/checker-rules/pool.json"
def build():
    hr, hi, ht = B.holdout_fingerprint(); ki, kt, kr = splits.answer_key()
    D = common.load(); C = {json.loads(l)["key"]: json.loads(l) for l in open(B.SW + "/corpus.jsonl")}
    R = {json.loads(l)["key"]: json.loads(l) for l in open(B.SW + "/results.jsonl")}
    rows = {}
    def add(repo, src, label, cats, strong, plug):
        files = read_tree(src)
        if not files: return
        fh = B.file_hashes(files); mid = (B.manifest_id(files) or "").lower()
        if repo in hr or repo in kr or mid in hi or mid in ki or B.near_dup(fh, ht) or B.near_dup(fh, kt): return
        rows[repo] = dict(repo=repo, src=src, label=label, cats_any=sorted(cats), cats_strong=sorted(strong), reviewed=plug)
    for p, v in D.items():
        repo = B.norm_repo(p); sha = v["sha"]; any_c = {c for x in v["findings"] for c in x["categories"]}
        # positives for a category: finding at the reviewed commit with strong/likely strength
        st = {c for x in v["gt"] if common.strength(x["fixed"]) in ("strong", "likely") for c in x["categories"]}
        src = os.path.join(fetch.CACHE, common.repo_of(p).replace("/", "__") + "@" + (sha or ""))
        lab = (R.get(common.repo_of(p)) or R.get(repo) or {}).get("label")
        if sha and os.path.exists(src + "/.ok"): add(repo, src, lab, any_c, st, True)
    for k, r in R.items():
        repo = B.norm_repo(k)
        if repo in rows or r.get("label") != "works": continue
        c = C.get(k) or {}; ld = c.get("local_dir")
        if ld and os.path.isdir(ld): add(repo, ld, "works", set(), set(), False)
    for r in rows.values():
        r["split"] = "test" if int(hashlib.sha1(("rules-v2:" + r["repo"]).encode()).hexdigest(), 16) % 10 < 3 else "design"
    json.dump(rows, open(OUT, "w"))
    print(len(rows), collections.Counter(r["split"] for r in rows.values()), collections.Counter(r["label"] for r in rows.values()))
if __name__ == "__main__": build()
