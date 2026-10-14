"""Read-only fetch of a plugin repo at a commit via the GitHub tarball API -> cache dir of text sources.
Usage: fetch(repo, sha) -> path or None. Keeps text files <=256KB with code/config extensions."""
import os, subprocess, tarfile, io, json, sys
CACHE = os.environ.get("HANCORE_CACHE", "/workspace/hancore_cache")
EXT = (".qml", ".js", ".mjs", ".sh", ".bash", ".py", ".json", ".lua", ".conf", ".toml", ".md", ".txt", ".yaml", ".yml", ".desktop", ".service", ".rules", ".ini", "qmldir", "PKGBUILD", "Makefile", ".zsh", ".fish", ".ts", ".css", ".rs", ".go", ".c", ".h", ".cpp")
def fetch(repo, sha):
    d = os.path.join(CACHE, repo.replace("/", "__") + "@" + sha)
    if os.path.exists(d + "/.ok"): return d
    if os.path.exists(d + "/.fail"): return None
    os.makedirs(d, exist_ok=True)
    try:
        b = subprocess.run(["gh", "api", f"repos/{repo}/tarball/{sha}"], capture_output=True, timeout=120).stdout
        t = tarfile.open(fileobj=io.BytesIO(b), mode="r:gz"); n = 0
        for m in t.getmembers():
            if not m.isfile() or m.size > 256_000: continue
            rel = m.name.split("/", 1)[1] if "/" in m.name else m.name
            if not rel.endswith(EXT) or "/node_modules/" in "/" + rel or rel.startswith(".git/"): continue
            data = t.extractfile(m).read()
            try: data.decode("utf-8")
            except UnicodeDecodeError: continue
            p = os.path.join(d, rel); os.makedirs(os.path.dirname(p), exist_ok=True); open(p, "wb").write(data); n += 1
        open(d + "/.ok", "w").write(str(n)); return d
    except Exception as e:
        open(d + "/.fail", "w").write(repr(e)[:300]); return None
def read_files(d):
    out = {}
    for root, _, fs in os.walk(d):
        for f in fs:
            if f in (".ok", ".fail"): continue
            p = os.path.join(root, f); out[os.path.relpath(p, d)] = open(p, encoding="utf-8", errors="replace").read()
    return out
if __name__ == "__main__":
    from concurrent.futures import ThreadPoolExecutor
    jobs = [l.split() for l in open(sys.argv[1]) if l.strip()]
    with ThreadPoolExecutor(12) as ex:
        res = list(ex.map(lambda j: fetch(*j), jobs))
    print("ok", sum(1 for r in res if r), "fail", sum(1 for r in res if not r))
