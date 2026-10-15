#!/usr/bin/env python3
"""Re-apply the CURRENT models/train/holdout_guard.py (repo, manifest id, content, per-file Jaccard, same-name, same-author vs the sealed holdout and the Dell key)
to the S1 / S2 plugin sets and write the flagged ids. Run after every guard or fingerprint update; flagged plugins must be dropped from the eval-only sets.

usage: python3 guard_recheck.py --models ../models --s2 s2_candidates.jsonl --s2-tree-root DIR --s1 s1_hw_items.jsonl --out guard_flags.json
"""
import argparse
import collections
import json
import os
import sys

SWEEP = "/workspace/usuba-model-checker/dell/sweep"


def tree(d):
    out = {}
    for r, ds, fs in os.walk(d):
        ds[:] = [x for x in ds if x not in (".git", "node_modules")]
        for f in fs:
            p = os.path.join(r, f)
            try:
                if os.path.islink(p) or os.path.getsize(p) > 400_000:
                    continue
                out[os.path.relpath(p, d)] = open(p, encoding="utf-8").read()
            except (OSError, UnicodeDecodeError):
                continue
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", required=True)
    ap.add_argument("--s2")
    ap.add_argument("--s2-tree-root")
    ap.add_argument("--s1")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    sys.path.insert(0, os.path.join(a.models, "train"))
    import holdout_guard as hg
    g = hg.Guard()
    flags = {"s2": {}, "s1": {}}
    if a.s2:
        for line in open(a.s2):
            c = json.loads(line)
            files = tree(os.path.join(a.s2_tree_root, c["job"]))
            w = g.check_row({"repo": c["repo"], "provenance": {"kind": "clean-registry"}}, files=files)
            if w:
                flags["s2"][c["plugin_id"]] = w
    if a.s1:
        corpus = {json.loads(line)["key"]: json.loads(line).get("local_dir") for line in open(f"{SWEEP}/corpus.jsonl")}
        seen = {}
        for line in open(a.s1):
            i = json.loads(line)
            if i["plugin"] in seen:
                continue
            files = tree(corpus.get(i["plugin"]) or "/nonexistent")
            w = g.check_row({"repo": i["plugin"], "provenance": {"kind": "clean-registry"}}, files=files)
            seen[i["plugin"]] = w
            if w:
                flags["s1"][i["plugin"]] = w
    flags["counts"] = {k: len(v) for k, v in flags.items() if isinstance(v, dict)}
    flags["reasons"] = dict(collections.Counter(w.split(":")[0] for k in ("s1", "s2") for w in flags[k].values()))
    json.dump(flags, open(a.out, "w"), indent=1)
    print(json.dumps({"counts": flags["counts"], "reasons": flags["reasons"]}))


if __name__ == "__main__":
    main()
