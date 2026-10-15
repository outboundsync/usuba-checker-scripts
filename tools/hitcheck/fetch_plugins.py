#!/usr/bin/env python3
"""Rebuild the plugin trees of the hit-check from public git repos (the trees themselves are not redistributed).

    python3 tools/hitcheck/fetch_plugins.py --out pkg [--only JOB ...] [--batch A|B]

For every job in plugins_manifest.json: fetch the repo (Batch B at the pinned commit; Batch A at the current HEAD, no commit was recorded),
copy the plugin root into pkg/plugins/<job>/ without .git, symlinks, files > 1 MB or ELF/PE binaries, and write pkg/jobs.tsv
(id, dir, plugin id, kinds), jobs.json and plugins-A/B.tar.gz, the package layout run_hitcheck.sh expects
(claims carry rule/file/line only, no code snippets). Only repos whose licence you are allowed to use should be run; the licence file of each tree is reported.
"""
import argparse, json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def run(*a, cwd=None):
    return subprocess.run(a, cwd=cwd, capture_output=True, text=True, timeout=300)


def is_binary(p):
    with open(p, "rb") as f:
        return f.read(4) in (b"\x7fELF", b"MZ\x90\x00")


def fetch(job, out, cache):
    repo = job["repo"]
    d = os.path.join(cache, repo.replace("/", "__") + "@" + (job.get("commit") or "HEAD"))
    if not os.path.isdir(d):
        os.makedirs(d)
        run("git", "init", "-q", cwd=d); run("git", "remote", "add", "origin", f"https://github.com/{repo}.git", cwd=d)
        r = run("git", "fetch", "-q", "--depth", "1", "origin", job.get("commit") or "HEAD", cwd=d)
        if r.returncode:
            shutil.rmtree(d); return None, "fetch failed"
        run("git", "checkout", "-q", "FETCH_HEAD", cwd=d)
    src = os.path.normpath(os.path.join(d, job.get("plugin_root", ".")))
    if not src.startswith(d) or not os.path.isdir(src):
        return None, "plugin root missing"
    dst = os.path.join(out, "plugins", job["job"])
    shutil.rmtree(dst, ignore_errors=True)
    for r_, ds, fs in os.walk(src):
        ds[:] = [x for x in ds if x != ".git"]
        for f in fs:
            p = os.path.join(r_, f)
            if os.path.islink(p) or os.path.getsize(p) > 1_000_000 or is_binary(p):
                continue
            t = os.path.join(dst, os.path.relpath(p, src)); os.makedirs(os.path.dirname(t), exist_ok=True); shutil.copy2(p, t)
    man = os.path.join(dst, "manifest.json")
    try:
        m = json.load(open(man)); pid = m.get("id", "?"); kinds = ",".join(m.get("kinds", []))
    except Exception:
        return None, "no valid manifest.json at plugin root"
    lic = [f for f in os.listdir(dst) if f.upper().startswith(("LICENSE", "LICENCE", "COPYING"))]
    return (job["job"], os.path.join("plugins", job["job"]), pid, kinds), ("licence file: " + lic[0] if lic else "NO LICENCE FILE at plugin root")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="pkg"); ap.add_argument("--only", nargs="*"); ap.add_argument("--batch", choices=["A", "B"])
    a = ap.parse_args()
    jobs = json.load(open(os.path.join(HERE, "plugins_manifest.json")))["jobs"]
    jobs = [j for j in jobs if (not a.only or j["job"] in a.only) and (not a.batch or j["batch"] == a.batch)]
    os.makedirs(a.out, exist_ok=True)
    cache = os.path.join(a.out, ".cache"); rows = []
    for j in jobs:
        row, note = fetch(j, a.out, cache); print(j["job"], "->", note)
        if row: rows.append(row)
    with open(os.path.join(a.out, "jobs.tsv"), "w") as f:
        f.write("".join("\t".join(r) + "\n" for r in rows))
    ok = {r[0] for r in rows}
    jj = [dict(j, dir="plugins/" + j["job"], root=".", claims=j.get("claims", [])) for j in jobs if j["job"] in ok]
    json.dump({"generated": "fetch_plugins.py", "jobs": jj}, open(os.path.join(a.out, "jobs.json"), "w"), indent=1)
    for b in "AB":
        names = ["plugins/" + j["job"] for j in jj if j["batch"] == b]
        if names: subprocess.run(["tar", "czf", os.path.join(a.out, f"plugins-{b}.tar.gz")] + names, cwd=a.out, check=True)
    for f in ("run_hitcheck.sh", "hc_signal.py", "analyze_results.py"):
        shutil.copy2(os.path.join(HERE, f), a.out)
    shutil.rmtree(cache, ignore_errors=True)
    print(f"{len(rows)}/{len(jobs)} jobs ready in {a.out}")
    sys.exit(0 if len(rows) == len(jobs) else 1)


if __name__ == "__main__":
    main()
