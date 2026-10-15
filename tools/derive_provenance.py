"""Derive provenance for committed result artefacts that were written before ``provenance.report_meta()`` existed (audit F5).

For each artefact: sha256, size, and the commits that touched it (``git log --follow``). The Checker that produced a file is *bounded*
by those commits: it is no newer than the last commit that wrote the file, and no older than the previous one. We never claim an exact
SHA that git cannot support; ``checker_sha_upper_bound`` is the last writing commit, ``confidence`` says how far to trust it.

Also verifies ``jankeesvw-history/v3fixes_wip_snapshot.sha256`` by locating, for every listed file, the commit whose blob has the
recorded sha256 (the snapshot predates this repo's current files, so ``sha256sum -c`` against the working tree cannot pass).

    python3 tools/derive_provenance.py            # write provenance/ARTIFACTS.json and provenance/SNAPSHOT_V3FIXES.json
    python3 tools/derive_provenance.py --check    # exit 1 if either file is stale or any snapshot hash has no matching commit
"""
import argparse
import glob
import hashlib
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARTIFACTS = ["functest/results.json", "functest/recal_registry.jsonl", "functest/ref49_results.json", "functest/calibration.json",
             "winners/checker_results.json", "winners/winners_profile.json", "jankeesvw-history/jv_rules_metrics.json",
             "jankeesvw-history/rows_stats.json", "jankeesvw-history/summary.json"] + sorted(
    os.path.relpath(p, REPO) for p in glob.glob(os.path.join(REPO, "results/hitcheck/*")))
SNAPSHOT = "jankeesvw-history/v3fixes_wip_snapshot.sha256"
# files in the snapshot that live in the sibling models repo (train/*); resolved when MODELS_REPO is given, else reported as unresolved
MODELS_REPO = os.environ.get("MODELS_REPO", os.path.join(os.path.dirname(REPO), "models"))


def git(repo, *args):
    p = subprocess.run(["git", "-C", repo, *args], capture_output=True, check=False, timeout=120)
    return p.returncode, p.stdout


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def artifact_entry(rel):
    with open(os.path.join(REPO, rel), "rb") as f:
        data = f.read()
    _, out = git(REPO, "log", "--follow", "--format=%H %aI", "--", rel)
    commits = [ln.split(" ", 1) for ln in out.decode().splitlines()]
    return {
        "path": rel, "sha256": sha256(data), "bytes": len(data),
        "commits": [{"sha": s, "date": d} for s, d in commits],
        "checker_sha_upper_bound": commits[0][0] if commits else None,
        "checker_sha_lower_bound": commits[-1][0] if commits else None,
        "confidence": ("single writing commit: Checker is that commit's parent tree plus uncommitted edits (dirty state unrecorded)"
                       if len(commits) == 1 else
                       "file rewritten/merged across several commits: rows may come from different Checker versions; re-run to get a single SHA"),
        "recorded_at_write_time": False,
    }


def snapshot_entries():
    res = []
    with open(os.path.join(REPO, SNAPSHOT)) as f:
        lines = [ln.split(None, 1) for ln in f.read().splitlines() if ln.strip()]
    for want, path in lines:
        path = path.strip()
        repo = REPO if not path.startswith("train/") else MODELS_REPO
        found = None
        if os.path.isdir(repo):
            _, revs = git(repo, "log", "--all", "--format=%H", "--", path)
            for r in revs.decode().split():
                rc, blob = git(repo, "show", f"{r}:{path}")
                if rc == 0 and sha256(blob) == want:
                    found = r
                    break
        res.append({"path": path, "sha256": want, "repo": "models" if path.startswith("train/") else "scripts", "matching_commit": found})
    return res


def build():
    return ({"note": "Derived bounds, not write-time records (F5). See docs/RELEASE_TAGS.md.", "artifacts": [artifact_entry(a) for a in ARTIFACTS]},
            {"note": "Snapshot hashes of the v3-fixes WIP tree, resolved to the commit holding each exact blob. Original .sha256 is kept as the "
                     "historical record; it cannot verify against HEAD because those files have since changed.", "files": snapshot_entries()})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    arts, snap = build()
    bad = [e["path"] for e in snap["files"] if e["matching_commit"] is None and (e["repo"] == "scripts" or os.path.isdir(MODELS_REPO))]
    outs = {"provenance/ARTIFACTS.json": arts, "provenance/SNAPSHOT_V3FIXES.json": snap}
    if a.check:
        # artefact hashes must match the committed provenance file; commit lists only grow, so compare sha256 only
        rc = 0
        old = json.load(open(os.path.join(REPO, "provenance/ARTIFACTS.json")))
        stale = [e["path"] for e in arts["artifacts"] if {x["path"]: x["sha256"] for x in old["artifacts"]}.get(e["path"]) != e["sha256"]]
        if stale:
            print("stale artefact provenance:", stale)
            rc = 1
        if bad:
            print("snapshot files with no matching commit:", bad)
            rc = 1
        return rc
    for rel, obj in outs.items():
        with open(os.path.join(REPO, rel), "w") as f:
            json.dump(obj, f, indent=1)
            f.write("\n")
    print("wrote", list(outs), "unresolved snapshot files:", bad)
    return 0


if __name__ == "__main__":
    sys.exit(main())
