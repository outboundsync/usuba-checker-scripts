#!/usr/bin/env python3
"""Re-run the recal_registry.jsonl rows that FAILED with the final code (later fixes only relaxed checks) and update them in place."""
import json, os, sys
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import recal_registry as R
rows = [json.loads(l) for l in open(R.OUT)]
scan = {json.loads(l)["id"]: json.loads(l) for l in open(R.SCAN)}
todo = [r["id"] for r in rows if r["new"] is False]
print("rerun", len(todo), flush=True)
with ThreadPoolExecutor(int(os.environ.get("J", "6"))) as ex:
    new = dict(zip(todo, ex.map(lambda i: R.one(scan[i]), todo)))
with open(R.OUT, "w") as f:
    for r in rows: f.write(json.dumps(dict(new.get(r["id"], r), rerun=r["id"] in new)) + "\n")
