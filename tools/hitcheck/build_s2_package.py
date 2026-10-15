#!/usr/bin/env python3
"""Build the S2 (clean-set) hardware smoke package (box side; nothing here touches the Dell).

S2 candidate = plugin that (1) the earlier Dell sweep labelled WORKS with a clean hardware record, (2) passes the CURRENT static Checker,
(3) is not in any training/validation row (r4, r5), the sealed holdout, or the sealed Dell key (repo id, manifest id AND file content, via models/train/holdout_guard.py).
Selection is stratified by plugin kind with a fixed seed. Output: jobs.json / jobs.tsv / plugins-A.tar.gz / plugins-B.tar.gz (empty) in the layout run_hitcheck.sh expects,
plus s2_candidates.jsonl (ids, repo, commit, kinds, Checker flags; no plugin code). The set is EVAL-ONLY: s2_exclude_from_training.txt lists the repos.

usage: python3 build_s2_package.py --models ../models-checkout --out OUTDIR [--n 280] [--seed 20261015]
"""
import argparse
import collections
import glob
import gzip
import io
import json
import os
import random
import re
import sys
import tarfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_package as bp  # noqa: E402  (copy_tree, plugin_root, read_manifest: shared tree-copy rules, no ELF/symlinks/oversize)

SWEEP = "/workspace/usuba-model-checker/dell/sweep"
QUOTA = {"panel": 70, "overlay": 60, "menu": 25, "bar": 20, "service": 45, "bar-widget": 60}   # by primary kind; hardware checklist matters most for surfaces that open
VALID = re.compile(r"^[A-Za-z0-9._-]+$")


def primary(kinds):
    for k in ("panel", "overlay", "menu", "bar", "service", "bar-widget"):
        if k in kinds:
            return k
    return "other"


def read_tree_texts(d):
    out = {}
    for r, ds, fs in os.walk(d):
        ds[:] = [x for x in ds if x not in (".git", "node_modules")]
        for f in fs:
            p = os.path.join(r, f)
            try:
                if os.path.islink(p) or os.path.getsize(p) > 400_000:
                    continue
                out[os.path.relpath(p, d)] = open(p, encoding="utf-8", errors="strict").read()
            except (OSError, UnicodeDecodeError):
                continue
    return out


def write_tars(out, stage, jobs):
    """two tarballs (each well under the 100 MiB copy limit), alternating jobs so both halves have the same mix; run_hitcheck.sh extracts both"""
    def norm(ti):
        ti.uid = ti.gid = 0
        ti.uname = ti.gname = ""
        return ti
    for i, b in enumerate("AB"):
        with tarfile.open(f"{out}/plugins-{b}.tar.gz", "w:gz", compresslevel=9) as t:
            ti = tarfile.TarInfo("plugins")
            ti.type = tarfile.DIRTYPE
            ti.mode = 0o755
            t.addfile(ti, io.BytesIO())
            for job in sorted(jobs)[i::2]:
                t.add(os.path.join(stage, job), arcname=f"plugins/{job}", filter=norm)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=280)
    ap.add_argument("--seed", type=int, default=20261015)
    ap.add_argument("--train-glob", action="append", default=[], help="extra training jsonl[.gz] files whose repos are excluded")
    a = ap.parse_args()
    sys.path.insert(0, os.path.join(a.models, "train"))
    import holdout_guard as hg
    sys.path.insert(0, os.path.join(HERE, "..", ".."))
    import usuba_checker as uc
    sys.path.insert(0, uc.functest_dir())

    train_repos = set()
    pats = ["/workspace/usuba-runs/v3-data-r5/*.jsonl*", "/workspace/usuba-runs/v3-data-r4/*.jsonl*"] + a.train_glob
    ntrain = 0
    for pat in pats:
        for f in glob.glob(pat):
            op = gzip.open if f.endswith(".gz") else open
            for line in op(f, "rt"):
                train_repos |= hg.row_repos(json.loads(line))
                ntrain += 1
    guard = hg.Guard()
    corpus = {json.loads(line)["key"]: json.loads(line) for line in open(f"{SWEEP}/corpus.jsonl")}
    res = [json.loads(line) for line in open(f"{SWEEP}/results.jsonl")]
    stats = collections.Counter()
    pool = []
    for r in res:
        stats["sweep rows"] += 1
        if r["label"] != "works" or not r.get("checker") or not r["checker"]["pass_"]:
            continue
        stats["works + old Checker pass"] += 1
        d = r.get("dell") or {}
        if not d or d.get("harness_invalid") or d.get("died") or d.get("listed") is False or d.get("toggle_ok") is False or d.get("qml_errors") or d.get("missing_bins") or d.get("leaked"):
            continue
        stats["clean Dell record (no qml errors, deps, leaks)"] += 1
        key = r["key"].lower()
        if key in train_repos:
            stats["excluded: in r4/r5 train/val"] += 1
            continue
        if key in guard.repos or (r["plugin_id"] or "").lower() in guard.mids | guard.dell_ids:
            stats["excluded: sealed holdout / Dell key (repo or id)"] += 1
            continue
        c = corpus.get(r["key"])
        if not c or not c.get("local_dir") or not os.path.isdir(c["local_dir"]):
            continue
        pool.append((r, c))
    stats["pool before content guard"] = len(pool)
    by = collections.defaultdict(list)
    for r, c in pool:
        by[primary(r["kinds"])].append((r, c))
    rng = random.Random(a.seed)
    chosen = []
    seen_repo = set()
    for kind, quota in QUOTA.items():
        L = sorted(by[kind], key=lambda x: x[0]["key"])
        rng.shuffle(L)
        got = 0
        for r, c in L:
            if got >= quota * 1.6:   # oversample: some fail the content guard / Checker / packaging below
                break
            if r["key"] in seen_repo or not VALID.match(r["plugin_id"] or "") or r["plugin_id"].startswith("b3.opus55."):
                continue
            seen_repo.add(r["key"])
            chosen.append((kind, quota, r, c))
            got += 1
    stats["oversampled"] = len(chosen)
    os.makedirs(a.out, exist_ok=True)
    stage = os.path.join(a.out, "stage", "plugins")
    jobs, cands, kept_per = [], [], collections.Counter()
    for kind, quota, r, c in chosen:
        if kept_per[kind] >= quota:
            continue
        src = c["local_dir"]
        root = bp.plugin_root(src)
        if root is None:
            stats["dropped: no manifest"] += 1
            continue
        # prefer the manifest whose id is the swept plugin id (monorepos)
        for m in bp.find_manifests(src):
            mm = bp.read_manifest(os.path.join(src, m, "manifest.json"))
            if mm and mm.get("id") == r["plugin_id"]:
                root = m
                break
        psrc = os.path.normpath(os.path.join(src, root))
        files = read_tree_texts(psrc)
        if guard.content_hits(files):
            stats["excluded: content matches holdout/Dell key"] += 1
            continue
        try:
            rep = uc.check_files(files)
        except Exception as e:  # noqa: BLE001 (Checker crash on a third-party tree: drop the plugin, count it)
            stats["dropped: Checker crashed " + type(e).__name__] += 1
            continue
        if not rep.get("pass"):
            stats["dropped: fails the CURRENT Checker"] += 1
            continue
        job = "s2-" + re.sub(r"[^A-Za-z0-9._-]+", "-", r["plugin_id"])[:70]
        dst = os.path.join(stage, job)
        os.makedirs(dst, exist_ok=True)
        dropped = bp.copy_tree(psrc, dst)
        kinds = r["kinds"] or []
        jobs.append(dict(job=job, plugin_id=r["plugin_id"], batch="A", kinds=kinds, dir=f"plugins/{job}", repo=r["key"], commit=r["commit"], plugin_root=root, claims=[], dropped=dropped[:20]))
        cands.append(dict(job=job, plugin_id=r["plugin_id"], repo=r["key"], commit=r["commit"], root=root, kinds=kinds, primary=kind, n_files=len(files),
                          checker_flags=[f[0] for f in rep.get("static_flags", [])][:10], checker_sha=rep["meta"]["checker_git_sha"], prior_dell_run=(r.get("dell") or {}).get("run")))
        kept_per[kind] += 1
    stats["candidates kept"] = len(cands)
    stats.update({f"kept {k}": v for k, v in kept_per.items()})
    json.dump(dict(generated="S2 hardware smoke package", seed=a.seed, jobs=jobs), open(f"{a.out}/jobs.json", "w"), indent=1)
    with open(f"{a.out}/jobs.tsv", "w") as f:
        for j in jobs:
            f.write("\t".join([j["job"], j["dir"], j["plugin_id"], ",".join(j["kinds"]) or "none"]) + "\n")
    with open(f"{a.out}/s2_candidates.jsonl", "w") as f:
        f.writelines(json.dumps(c) + "\n" for c in cands)
    with open(f"{a.out}/s2_exclude_from_training.txt", "w") as f:
        f.writelines(c["repo"].lower() + "\n" for c in cands)
    write_tars(a.out, stage, [j["job"] for j in jobs])
    json.dump(dict(stats), open(f"{a.out}/s2_selection_stats.json", "w"), indent=1)
    print(json.dumps(stats, indent=1), f"\ntrain rows scanned: {ntrain}; train repos: {len(train_repos)}")


if __name__ == "__main__":
    main()
