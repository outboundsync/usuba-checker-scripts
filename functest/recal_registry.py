#!/usr/bin/env python3
"""Re-run the (new) functest over the registry scan (clean/registry/scan.jsonl). Resumable; writes recal_registry.jsonl.
Old pass rate = scan.jsonl pass_ (742/1000 = 74.2%). Passing repos are cloned at /workspace/registry_repos/<id>;
old FAILS were not kept on disk, so a random sample of them is re-cloned at the scanned commit (--fails N)."""
import json, os, sys, random, subprocess, time
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); sys.path.insert(0, HERE)
import functest
SCAN = os.path.join(ROOT, "clean/registry/scan.jsonl"); OUT = os.path.join(HERE, "recal_registry.jsonl")
REPOS = "/workspace/registry_repos"; FAILREPOS = "/workspace/registry_repos_oldfail"
def clone(r):
    d = os.path.join(FAILREPOS, r["id"])
    if os.path.isdir(d): return d
    os.makedirs(FAILREPOS, exist_ok=True)
    try:
        subprocess.run(["git", "clone", "-q", "--filter=blob:none", r["repo"], d], timeout=120, check=True, capture_output=True)
        subprocess.run(["git", "-C", d, "checkout", "-q", r["commit"]], timeout=60, check=True, capture_output=True)
        return d
    except Exception: return None
def one(r):
    d = os.path.join(REPOS, r["id"]) if r["pass_"] else clone(r)
    if not d or not os.path.exists(os.path.join(d, "manifest.json")): return {"id": r["id"], "old": r["pass_"], "new": None}
    t = time.time(); x = functest.test(src_dir=d)
    return {"id": r["id"], "old": r["pass_"], "new": x["pass"], "categories": x["categories"], "static_fails": x["static_fails"][:6],
            "runtime_errors": ((x["runtime"] or {}).get("errors") or [])[:6], "checks": {k: v for k, v in ((x["runtime"] or {}).get("checks") or {}).items() if k != "texts"},
            "secs": round(time.time() - t)}
if __name__ == "__main__":
    nf = int(sys.argv[sys.argv.index("--fails") + 1]) if "--fails" in sys.argv else 0
    rows = [json.loads(l) for l in open(SCAN)]
    done = {json.loads(l)["id"] for l in open(OUT)} if os.path.exists(OUT) else set()
    todo = [r for r in rows if r["pass_"] and os.path.isdir(os.path.join(REPOS, r["id"]))]
    fails = [r for r in rows if not r["pass_"]]; random.Random(7).shuffle(fails); todo += fails[:nf]
    todo = [r for r in todo if r["id"] not in done]
    print("todo", len(todo), flush=True)
    with ThreadPoolExecutor(int(os.environ.get("J", "6"))) as ex, open(OUT, "a") as f:
        for i, res in enumerate(ex.map(one, todo)):
            f.write(json.dumps(res) + "\n"); f.flush()
            if i % 25 == 0: print(i, res["id"], res.get("new"), res.get("categories"), flush=True)
