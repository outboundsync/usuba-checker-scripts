#!/usr/bin/env python3
"""Build the Dell hit-check package (box side; nothing here touches the Dell).
Batch A: Checker rule hit-check. For every rule enabled on branch v3-fixes (USB-HC01,02,04,05,08,09,10,15,16,17,19,20,25 + lifecycle USB-L02,L03,N01,N02)
  about 20 plugins whose hit still fires under the CURRENT rule code, taken first from usuba-runs/checker-rules/dell_confirm_candidates.json (seeded samples,
  v2 ids USB-H* map to USB-HC*), topped up from the cached current-code hits (hits_hc_after.jsonl) with a fixed seed. Plus skip-rule cases: hits the OLD
  code produced that the v3-fixes skip conditions now suppress (incl. the winners report cases), expected defect NOT observable.
Batch B: version-history pairs (pre-fix = parent commit, post-fix = fix commit) from verified_pairs.jsonl, permissive (MIT/ISC/BSD) licences only.
Exclusions (ids/paths only, labels never read): Dell answer-key ids + near-duplicate trees, hancore_holdout repos/ids/trees, jankeesvw repos.
usage: python3 build_package.py [--runs-dir DIR | $USUBA_RUNS_DIR] [--out DIR] [--per-rule 20] [--pairs 30]"""
import os, sys, re, json, io, hashlib, random, shutil, subprocess, tarfile, argparse, collections, tempfile
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
# Root of the run artifacts (checker-rules/, v3-fixes/, version-history/ ...). Set with --runs-dir or $USUBA_RUNS_DIR;
# default: a sibling "usuba-runs" directory next to this repo checkout (<repo>/../usuba-runs).
R = os.environ.get("USUBA_RUNS_DIR") or os.path.join(os.path.dirname(REPO), "usuba-runs")
sys.path[:0] = [REPO + "/functest/usuba", REPO + "/functest", REPO + "/hancore", REPO + "/train", REPO + "/train/v2"]
MAXFILE = 1_000_000; MAXTREE = 6_000_000
SKIPDIR = {".git", "node_modules", "target", "__pycache__", ".venv", "venv", "dist", ".github"}
H2HC = lambda r: r.replace("USB-H", "USB-HC") if re.match(r"USB-H\d\d$", r) else r
ENABLED_HC = ["USB-HC01", "USB-HC02", "USB-HC04", "USB-HC05", "USB-HC08", "USB-HC09", "USB-HC10", "USB-HC15", "USB-HC16", "USB-HC17", "USB-HC19", "USB-HC20", "USB-HC25"]
ENABLED_LIFE = ["USB-L02", "USB-L03", "USB-N01", "USB-N02"]
CHECKER_V2_REF = os.environ.get("CHECKER_V2_REF", "8754bc4d8900814697f7fc951b3b8521a77b17eb")   # branch checker-rules-v2 no longer exists in this repo (audit J)
SKIP_RULES_OLD = ["USB-H01", "USB-H02", "USB-H06", "USB-H24", "USB-H18"]   # rules the v3-fixes skip conditions touch (H06/H18/H24 are experimental/dropped)

def tar_extract(t, member=None, path="."):
    """extract with the 'data' filter where this Python has it (3.12+, and the 3.8.17/3.9.17/3.10.12/3.11.4 backports); older 3.10 patch releases
    have no filter= argument, so refuse unsafe members (absolute/.. paths, links, devices) by hand and extract without it."""
    kw = {"filter": "data"} if hasattr(tarfile, "data_filter") else {}
    members = [member] if member is not None else t.getmembers()
    if not kw:
        root = os.path.realpath(path)
        for m in members:
            dest = os.path.realpath(os.path.join(path, m.name))
            if os.path.isabs(m.name) or (dest != root and not dest.startswith(root + os.sep)) or m.issym() or m.islnk() or m.isdev():
                raise tarfile.TarError("unsafe tar member refused: %r" % m.name)
    for m in members: t.extract(m, path, **kw)

def slug(s): return re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-")[:60]
def sh(*a, **k): return subprocess.run(a, capture_output=True, **k)

def copy_tree(src, dst):
    """copy a plugin tree: no .git/node_modules/target, no symlinks, no files > 1 MB, no ELF/PE binaries, <= 6 MB total. returns dropped list."""
    dropped = []; total = 0; files = []
    for r, ds, fs in os.walk(src):
        ds[:] = sorted(d for d in ds if d not in SKIPDIR)
        for f in sorted(fs):
            p = os.path.join(r, f); rel = os.path.relpath(p, src)
            if os.path.islink(p): dropped.append(rel + " (symlink)"); continue
            sz = os.path.getsize(p)
            if sz > MAXFILE: dropped.append(rel + f" ({sz} B)"); continue
            try: head = open(p, "rb").read(4)
            except Exception: continue
            if head[:4] in (b"\x7fELF", b"MZ\x90\x00") or head[:2] == b"MZ": dropped.append(rel + " (binary)"); continue
            files.append((rel, sz))
    for rel, sz in sorted(files, key=lambda x: (not x[0].endswith((".qml", ".js", ".json", ".sh", ".py", ".lua", ".md")), x[1])):
        if total + sz > MAXTREE: dropped.append(rel + " (tree cap)"); continue
        total += sz; d = os.path.join(dst, rel); os.makedirs(os.path.dirname(d), exist_ok=True); shutil.copy2(os.path.join(src, rel), d)
    return dropped

def find_manifests(src):
    out = []
    for r, ds, fs in os.walk(src):
        ds[:] = [d for d in ds if d not in SKIPDIR]
        if r[len(src):].count("/") > 3: ds[:] = []
        if "manifest.json" in fs: out.append(os.path.relpath(r, src))
    return out
def read_manifest(p):
    try:
        m = json.load(open(p))
        return m if isinstance(m, dict) and isinstance(m.get("id"), str) else None
    except Exception: return None
def plugin_root(src, hit_file=None):
    ms = find_manifests(src)
    good = [m for m in ms if read_manifest(os.path.join(src, m, "manifest.json"))]
    if not good: return None
    if "." in good and read_manifest(os.path.join(src, "manifest.json")).get("entryPoints") is not None: return "."
    if hit_file:
        c = [m for m in good if m != "." and hit_file.startswith(m + "/")]
        if c: return max(c, key=len)
    return "." if "." in good else good[0]

def read_tree(d):
    out = {}
    for r, ds, fs in os.walk(d):
        ds[:] = [x for x in ds if x not in (".git", "node_modules")]
        for f in fs:
            p = os.path.join(r, f)
            try:
                if os.path.islink(p) or os.path.getsize(p) > 400_000: continue
                out[os.path.relpath(p, d)] = open(p, encoding="utf-8", errors="strict").read()
            except Exception: pass
    return out

def current_hits(files):
    import hancore_rules_v2 as V, lifecycle_rules as L
    hits = [dict(rule=x["rule"], file=x["file"], line=x["line"]) for x in V.check(files, enabled=set(V.RULES), per_file=50)]
    try: hits += [dict(rule=x["rule"], file=x["file"], line=x["line"]) for x in L.check(files, enabled=set(L.RULES))]
    except Exception as e: print("lifecycle check error", e, file=sys.stderr)
    return hits

OLD_RUNNER = r'''
import sys, json, os
sys.path[:0] = [sys.argv[1] + "/functest/usuba", sys.argv[1] + "/functest"]
import hancore_rules_v2 as V
def rt(d):
    out = {}
    for r, ds, fs in os.walk(d):
        ds[:] = [x for x in ds if x not in (".git", "node_modules")]
        for f in fs:
            p = os.path.join(r, f)
            try:
                if os.path.islink(p) or os.path.getsize(p) > 400000: continue
                out[os.path.relpath(p, d)] = open(p, encoding="utf-8").read()
            except Exception: pass
    return out
res = {}
for d in sys.argv[2:]:
    res[d] = [dict(rule=x["rule"], file=x["file"], line=x["line"]) for x in V.check(rt(d), enabled=set(V.RULES), per_file=50)]
print(json.dumps(res))
'''
def old_hits(dirs):
    """hits of the pre-skip rule code (CHECKER_V2_REF = the former branch checker-rules-v2; this repo's commit 8754bc4) on given trees"""
    tmp = tempfile.mkdtemp(prefix="oldcr2.")
    p = subprocess.run(["git", "-C", REPO, "archive", CHECKER_V2_REF, "functest"], capture_output=True)   # no shell (audit C3)
    if p.returncode: raise SystemExit("git archive %s failed: " % CHECKER_V2_REF + p.stderr.decode())
    with tarfile.open(fileobj=io.BytesIO(p.stdout)) as t: tar_extract(t, path=tmp)
    q = subprocess.run([sys.executable, "-c", OLD_RUNNER, tmp] + dirs, capture_output=True, text=True)
    shutil.rmtree(tmp, ignore_errors=True)
    if q.returncode: raise SystemExit("old runner failed: " + q.stderr[-500:])
    return json.loads(q.stdout)

def exclusions():
    import splits, build_train_set as B
    ki, kt, kr = splits.answer_key(); hr, hi, ht = B.holdout_fingerprint()
    return dict(B=B, key_ids=ki, key_trees=kt, hold_repos=hr, hold_ids=hi, hold_trees=ht)

def excluded(X, repo, tree_files, mid):
    B = X["B"]; rl = B.norm_repo(repo) if repo else ""
    if "jankeesvw" in repo.lower(): return "jankeesvw"
    if rl in X["hold_repos"] or repo.lower() in X["hold_repos"]: return "holdout-repo"
    if mid and mid.lower() in X["hold_ids"]: return "holdout-id"
    if mid and mid.lower() in X["key_ids"]: return "dell-key-id"
    fh = B.file_hashes(tree_files)
    if fh and B.near_dup(fh, X["hold_trees"]): return "holdout-tree"
    if fh and B.near_dup(fh, X["key_trees"]): return "dell-key-tree"
    return None

def main():
    global R
    ap = argparse.ArgumentParser(); ap.add_argument("--runs-dir", default=None, help="run-artifacts root (default: $USUBA_RUNS_DIR, else <repo>/../usuba-runs)")
    ap.add_argument("--out", default=None, help="output dir (default: <runs-dir>/dell-hitcheck)"); ap.add_argument("--per-rule", type=int, default=20); ap.add_argument("--pairs", type=int, default=30)
    ap.add_argument("--seed", default="dell-hitcheck-1"); a = ap.parse_args()
    if a.runs_dir: R = os.path.abspath(a.runs_dir)
    if not os.path.isdir(R): raise SystemExit("runs dir not found: %s (pass --runs-dir or set USUBA_RUNS_DIR)" % R)
    OUT = a.out or R + "/dell-hitcheck"; os.makedirs(OUT, exist_ok=True); STAGE = OUT + "/_stage"; shutil.rmtree(STAGE, ignore_errors=True); os.makedirs(STAGE + "/A/plugins"); os.makedirs(STAGE + "/B/plugins")
    X = exclusions(); B = X["B"]
    rnd = random.Random(a.seed)
    pool = json.load(open(R + "/checker-rules/pool.json"))
    pool_by_lower = {k.lower(): v for k, v in pool.items()}
    cand = json.load(open(R + "/checker-rules/dell_confirm_candidates.json"))["rules"]
    after = {json.loads(l)["repo"].lower(): json.loads(l)["hits"] for l in open(R + "/v3-fixes/hits_hc_after.jsonl")}
    life = {json.loads(l)["repo"].lower(): json.loads(l)["hits"] for l in open(R + "/v3-fixes/hits_lifecycle.jsonl")}
    before = {json.loads(l)["repo"].lower(): json.loads(l)["hits"] for l in open(R + "/checker-rules/hits.jsonl")}
    for l in open(R + "/checker-rules/hits_model.jsonl"):
        d = json.loads(l); before.setdefault(d["repo"].lower(), []); before[d["repo"].lower()] += d["hits"]
    _cur = {}
    def cur(src):
        if src not in _cur: _cur[src] = current_hits(read_tree(src))
        return _cur[src]
    jobs = {}     # job -> dict(src, root, repo, claims=[...])
    def add_claim(repo, src, rule, file, line, group, **kw):
        job = "a-" + slug(repo.replace("/", "__"))
        j = jobs.setdefault(job, dict(job=job, repo=repo, src=src, claims=[]))
        if any(c["rule"] == rule and c["file"] == file and c["group"] == group for c in j["claims"]): return
        j["claims"].append(dict(rule=rule, file=file, line=line, group=group, **kw))
    def snippet_of(src, file, line):
        try:
            L = open(os.path.join(src, file), errors="replace").read().splitlines(); return "\n".join(L[max(0, line - 2):line + 1])[:300]
        except Exception: return ""
    # ---- A1: enabled HC rules, 20 plugins that still fire
    chosen = collections.defaultdict(list); skipcases = []
    for hc in ENABLED_HC:
        old = hc.replace("USB-HC", "USB-H"); have = set()
        for s in cand.get(old, {}).get("samples", []):
            repo = s["repo"]; src = s["plugin_src_path"]
            hit_now = [h for h in cur(src) if h["rule"] == hc]   # recomputed with the current code (the cached after-hits lost every hit of a plugin on which USB-HC17 raised, see docs)
            same = [h for h in hit_now if h["file"] == s["file"]]
            if hit_now and len(chosen[hc]) < a.per_rule:
                h = (same or hit_now)[0]; chosen[hc].append(dict(repo=repo, src=src, file=h["file"], line=h["line"], origin="prepared_sample", hancore_status=s.get("hancore_status")))
                have.add(repo.lower())
            elif not hit_now: skipcases.append(dict(rule=hc, repo=repo, src=src, file=s["file"], line=s["line"], origin="prepared_sample_now_skipped"))
        extra = []
        for repo, hits in after.items():
            if repo in have or repo not in pool_by_lower: continue
            hs = [h for h in hits if h["rule"] == hc]
            if hs: extra.append((hashlib.sha1((a.seed + hc + repo).encode()).hexdigest(), repo, hs[0]))
        for _, repo, h in sorted(extra):
            if len(chosen[hc]) >= a.per_rule: break
            p = pool_by_lower[repo]; chosen[hc].append(dict(repo=p["repo"], src=p["src"], file=h["file"], line=h["line"], origin="topup_current_hits", hancore_status=None))
    # lifecycle L02 (all pool hits)
    for repo, hits in life.items():
        hs = [h for h in hits if h["rule"] == "USB-L02"]
        if hs and repo in pool_by_lower:
            p = pool_by_lower[repo]; chosen["USB-L02"].append(dict(repo=p["repo"], src=p["src"], file=hs[0]["file"], line=hs[0]["line"], origin="pool_current_hits", hancore_status=None))
    # ---- A2: more skip cases from old-vs-new hits on the pool (rules touched by skip conditions), seeded, max 5 per old rule
    cnt = collections.Counter(s["rule"] for s in skipcases)
    for old in SKIP_RULES_OLD:
        new = H2HC(old); pairs = []
        for repo, hits in before.items():
            if repo not in pool_by_lower: continue
            for h in hits:
                if h["rule"] != old: continue
                if not any(x["rule"] == new and x["file"] == h["file"] and abs(x["line"] - h["line"]) <= 1 for x in after.get(repo, [])):
                    pairs.append((hashlib.sha1((a.seed + "skip" + old + repo).encode()).hexdigest(), repo, h)); break
        for _, repo, h in sorted(pairs)[:5]:
            p = pool_by_lower[repo]
            if not any(s["repo"].lower() == repo and s["rule"] == new for s in skipcases):
                skipcases.append(dict(rule=new, repo=p["repo"], src=p["src"], file=h["file"], line=h["line"], origin="pool_old_vs_new"))
    # ---- materialise A: resolve plugin root, check exclusions, copy
    notes = dict(rejected=[], no_manifest=[])
    def materialise(job, j):
        src = j["src"]; first = j["claims"][0]["file"]
        root = plugin_root(src, first)
        if root is None: notes["no_manifest"].append(j["repo"]); return None
        psrc = os.path.normpath(os.path.join(src, root)); m = read_manifest(psrc + "/manifest.json")
        files = read_tree(psrc); why = excluded(X, j["repo"], files, m["id"])
        if why: notes["rejected"].append((j["repo"], why)); return None
        dst = f"{STAGE}/A/plugins/{job}"; dropped = copy_tree(psrc, dst)
        return dict(root=root, plugin_id=m["id"], kinds=m.get("kinds") if isinstance(m.get("kinds"), list) else [], dropped=dropped[:12], n_dropped=len(dropped))
    for hc, lst in chosen.items():
        for c in lst:
            add_claim(c["repo"], c["src"], hc, c["file"], c["line"], "rule_sample", origin=c["origin"], hancore_status=c.get("hancore_status"), expect_fires=True)
    for s in skipcases:
        add_claim(s["repo"], s["src"], s["rule"], s["file"], s["line"], "skip_case", origin=s["origin"], expect_fires=False)
    # winners skip-rule cases (report section 4): radio-atlas (H01 /dev/null, H24 hyprctl eval, H06 mktemp, H18 helper curl, H02 readline), omapods (H02 vendored), github (H06 mktemp), omagotchi
    W = [("aksharp5/omarchy-radio-atlas", "/workspace/sweep_repos/aksharp5__omarchy-radio-atlas"), ("thisisgm/omarchy-pods", "/workspace/sweep_repos/thisisgm__omarchy-pods"),
         ("robzolkos/omarchy-github", "/workspace/sweep_repos/robzolkos__omarchy-github"), ("slcode777/omagotchi", "/workspace/sweep_repos/slcode777__omagotchi")]
    wold = old_hits([p for _, p in W])
    for repo, p in W:
        wnew = current_hits(read_tree(p))
        for h in wold[p]:
            nh = H2HC(h["rule"])
            if not any(x["rule"] == nh and x["file"] == h["file"] for x in wnew):
                add_claim(repo, p, nh, h["file"], h["line"], "skip_case", origin="winners_report_old_vs_new", expect_fires=False)
    # synthetic lifecycle plugins (own work): L03, N01 x2, N02 as rule samples, clean ones as controls
    sys.path.insert(0, REPO + "/train/v3data")
    import synthetic_lifecycle as S
    syn_keep = {"syn.qml.required-injected-property": "USB-L03", "syn.manifest.kind-without-key": "USB-N01", "syn.manifest.kind-used-as-key": "USB-N01", "syn.manifest.no-schema-version": "USB-N02"}
    syn_ctl = ["syn.ok.panel-open-close", "syn.ok.overlay-open-close", "syn.ok.bash-c-shellquote", "syn.ok.mktemp-guarded-cleanup"]
    synjobs = {}
    for sp in S.SPECS:
        if sp["id"] in syn_keep or sp["id"] in syn_ctl:
            job = "a-" + slug(sp["id"]); d = f"{STAGE}/A/plugins/{job}"
            for rel, txt in sp["files"].items():
                os.makedirs(os.path.dirname(os.path.join(d, rel)), exist_ok=True); open(os.path.join(d, rel), "w").write(txt)
            try: m = json.loads(sp["files"]["manifest.json"])
            except Exception: m = {}
            rule = syn_keep.get(sp["id"])
            synjobs[job] = dict(job=job, repo="synthetic/" + sp["id"], plugin_id=m.get("id"), kinds=m.get("kinds", []), root=".", dropped=[], n_dropped=0,
                                claims=[dict(rule=rule, file=("manifest.json" if rule and rule.startswith("USB-N") else list(sp["files"])[1]), line=0, group="rule_sample" if rule else "clean_control", origin="synthetic_lifecycle", expect_fires=bool(rule))])
    # materialise
    final = {}
    for job, j in sorted(jobs.items()):
        info = materialise(job, j)
        if info: final[job] = dict(j, **info)
    # rule claims for each final plugin: add what the CURRENT code fires on the staged tree (cross-check) + old code for skip cases
    for job, j in final.items():
        psrc = os.path.normpath(os.path.join(j["src"], j["root"])); files = read_tree(f"{STAGE}/A/plugins/{job}")
        hits = current_hits(files); j["current_hits"] = [h for h in hits if h["rule"] in ENABLED_HC + ENABLED_LIFE][:30]
        keep = []
        for c in j["claims"]:
            f = c["file"]
            if j["root"] != "." and f.startswith(j["root"] + "/"): f = f[len(j["root"]) + 1:]
            c["file"] = f
            same = [h for h in hits if h["rule"] == c["rule"] and h["file"] == f]
            c["fires_now"] = bool(same) if c["group"] != "skip_case" else any(abs(h["line"] - c["line"]) <= 1 for h in same)   # skip cases: line-level (the old hit must be gone)
            if c["fires_now"] != c["expect_fires"]: notes["rejected"].append((j["repo"] + ":" + c["rule"] + ":" + c["group"], "claim does not match current code")); continue
            c["snippet"] = snippet_of(f"{STAGE}/A/plugins/{job}", f, c["line"]) if c["line"] else ""
            c["file_present"] = os.path.exists(f"{STAGE}/A/plugins/{job}/{f}"); keep.append(c)
        j["claims"] = keep
        j.pop("src", None)
    for job in [k for k, v in final.items() if not v["claims"]]:
        shutil.rmtree(f"{STAGE}/A/plugins/{job}", ignore_errors=True); del final[job]
    final.update(synjobs)
    # ---- Batch B: version-history pairs
    pairs = select_pairs(a, X, STAGE)
    # ---- write jobs + tarballs
    jobsA = [dict(batch="A", **{k: v for k, v in j.items()}) for j in final.values()]
    jobsB = pairs
    allj = jobsA + jobsB
    for j in allj: j["dir"] = f"plugins/{j['job']}"
    json.dump(dict(generated="dell-hitcheck package", seed=a.seed, jobs=allj, notes=dict(rejected=notes["rejected"], no_manifest=notes["no_manifest"])), open(OUT + "/jobs.json", "w"), indent=1)
    with open(OUT + "/jobs.tsv", "w") as f:
        for j in allj: f.write("\t".join([j["job"], j["dir"], j["plugin_id"], ",".join(j["kinds"]) or "none"]) + "\n")
    for b in "AB":
        tp = f"{OUT}/plugins-{b}.tar.gz"
        with tarfile.open(tp, "w:gz", compresslevel=9) as t: t.add(f"{STAGE}/{b}/plugins", arcname="plugins", filter=lambda ti: (setattr(ti, "uid", 0), setattr(ti, "gid", 0), setattr(ti, "uname", ""), setattr(ti, "gname", ""), ti)[-1])
    shutil.rmtree(STAGE)
    print("A jobs", len(jobsA), "B jobs", len(jobsB), "rejected", len(notes["rejected"]), "no manifest", len(notes["no_manifest"]))

PRE_KINDS = [("syntax-or-parse-error", 3), ("api-compat-change", 5), ("null-or-missing-guard", 3), ("wrong-path-or-command", 3), ("error-handling", 3), ("process-or-resource-lifecycle", 3),
             ("env-or-config-assumption", 2), ("race-or-timing", 2), ("missing-dependency-or-install", 1), ("ui-layout-or-state", 2), ("wrong-condition-or-logic", 2), ("security", 1)]
OK_LIC = {"MIT", "ISC", "BSD"}
def select_pairs(a, X, STAGE):
    B = X["B"]; rows = [json.loads(l) for l in open(R + "/version-history/data/verified_pairs.jsonl")]
    VH = "/workspace/vh_repos"
    def git(repo, *args): return subprocess.run(["git", "-C", f"{VH}/{repo}"] + list(args), capture_output=True)
    def tree_at(repo, rev):
        p = git(repo, "ls-tree", "-r", "--name-only", rev)
        return p.stdout.decode().splitlines() if p.returncode == 0 else None
    def pick_root(names, f):
        mans = [n for n in names if n.endswith("manifest.json") and n.count("/") <= 3]
        roots = [os.path.dirname(n) or "." for n in mans]
        c = [r for r in roots if r == "." or f.startswith(r + "/")]
        return max(c, key=len) if c else None
    def archive(repo, rev, root, dst):
        os.makedirs(dst, exist_ok=True); spec = [rev] + ([root] if root != "." else [])
        p = subprocess.run(["git", "-C", f"{VH}/{repo}", "archive", "--format=tar"] + spec, capture_output=True)
        if p.returncode: return None
        tmp = dst + ".raw"; os.makedirs(tmp, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(p.stdout)) as t:
            for m in t.getmembers():
                if m.issym() or m.islnk() or m.isdev(): continue
                m.name = m.name; tar_extract(t, m, tmp)
        base = tmp if root == "." else os.path.join(tmp, root)
        dropped = copy_tree(base, dst); shutil.rmtree(tmp); return dropped
    good = []
    for r in rows:
        if r["license"] not in OK_LIC or "jankeesvw" in r["repo"].lower() or not r["file"].endswith((".qml", ".js", ".sh", ".py", ".lua")): continue
        if "cpp" in r["file"] or r["file"].startswith(("docs/", "tests/", "test/")): continue
        good.append(r)
    random.Random(a.seed).shuffle(good)
    def prio(r):
        f = r["file"]; return (0 if f.endswith(".qml") else 1 if f.endswith(".js") else 2, abs(len(r["removed"]) + len(r["added"])) > 8, -r.get("confidence", 0))
    by = collections.defaultdict(list)
    for r in sorted(good, key=prio): by[r["bug_kind"]].append(r)
    out = []; used = set(); n = 0
    for kind, quota in PRE_KINDS:
        got = 0
        for r in by.get(kind, []):
            if got >= quota or len(out) >= 2 * a.pairs: break
            if r["repo"] in used: continue
            names0 = tree_at(r["repo"], r["parent"]); names1 = tree_at(r["repo"], r["commit"])
            if not names0 or not names1: continue
            root = pick_root(names1, r["file"]); root0 = pick_root(names0, r["file"])
            if not root or root != root0: continue
            n += 1; job = f"b{n:02d}-{slug(r['repo'])[:40]}"
            ok = True; metas = {}
            for side, rev in (("pre", r["parent"]), ("post", r["commit"])):
                dst = f"{STAGE}/B/plugins/{job}-{side}"; d = archive(r["repo"], rev, root, dst)
                m = read_manifest(dst + "/manifest.json") if d is not None else None
                if m is None: ok = False; break
                metas[side] = dict(m=m, dropped=d)
            if ok:
                mid = metas["post"]["m"]["id"]
                if metas["pre"]["m"]["id"] != mid: ok = False
                why = excluded(X, r["repo"], read_tree(f"{STAGE}/B/plugins/{job}-post"), mid) if ok else "bad"
                if why: ok = False
            if not ok:
                for side in ("pre", "post"): shutil.rmtree(f"{STAGE}/B/plugins/{job}-{side}", ignore_errors=True)
                continue
            used.add(r["repo"]); got += 1
            for side in ("pre", "post"):
                m = metas[side]["m"]
                out.append(dict(batch="B", job=f"{job}-{side}", pair=job, side=side, repo=r["repo"], commit=r["commit"], parent=r["parent"], license=r["license"], bug_kind=r["bug_kind"], subject=r["subject"],
                                file=(r["file"][len(root) + 1:] if root != "." else r["file"]), pre_fix_line=r["pre_fix_line"] if "pre_fix_line" in r else None, defect=r["defect"], fix=r["fix"],
                                plugin_id=m["id"], kinds=m.get("kinds") if isinstance(m.get("kinds"), list) else [], root=root, dropped=metas[side]["dropped"][:8], n_dropped=len(metas[side]["dropped"])))
    # trim to the requested number of pairs, keeping the quota order
    names = []; [names.append(j["pair"]) for j in out if j["pair"] not in names]
    keep = set(names[:a.pairs])
    for j in out:
        if j["pair"] not in keep:
            shutil.rmtree(f"{STAGE}/B/plugins/{j['job']}", ignore_errors=True)
    return [j for j in out if j["pair"] in keep]
if __name__ == "__main__": main()
