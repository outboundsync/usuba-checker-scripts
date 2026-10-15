#!/usr/bin/env python3
"""Build concrete-bug labels from HANCORE strong/likely findings (non-holdout, non-Dell-key plugins).
Read-only over existing data. Parse file/line/kind with regex, verify against source at the reviewed commit.
No model calls. Never reads Dell key labels (only id/path of functest/dell_ground_truth.jsonl, all 116 rows, to exclude).
Outputs -> /workspace/usuba-runs/hancore-labels/"""
import sys, os, posixpath, re, json, hashlib, subprocess, collections, tarfile, io
H = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(H); sys.path.insert(0, H)
import common
from findings_v3 import KINDS, CLEAN_RE
OUT = "/workspace/usuba-runs/hancore-labels"; CACHE = "/workspace/hancore_cache"
K13 = ["install-deps-packaging", "unbounded-input-resource", "file-safety-symlink-perms", "secrets-credentials", "privileged-system",
       "process-lifecycle-timeouts", "remote-code-pinning", "url-scheme-network", "rich-text-markup-injection", "listing-metadata-docs",
       "user-config-modification", "shell-lua-injection", "runtime-qml-api-compat"]
norm = lambda s: s.lower().rstrip("/").removesuffix(".git").split("github.com/")[-1]
def fp_dir(files):  # files: {rel: text} -> set of (basename, sha1)
    return {(os.path.basename(k), hashlib.sha1(v.encode("utf-8", "replace")).hexdigest()[:12]) for k, v in files.items() if not k.startswith(".")}
def read_dir(d):
    out = {}
    for r, _, fs in os.walk(d):
        if "/.git" in r: continue
        for f in fs:
            if f in (".ok", ".fail"): continue
            p = os.path.join(r, f)
            try:
                if os.path.getsize(p) > 400_000: continue
                out[os.path.relpath(p, d)] = open(p, encoding="utf-8").read()
            except Exception: pass
    return out
corpus = [json.loads(l) for l in open(os.path.join(ROOT, "dell/sweep/corpus.jsonl"))]
by_repo = collections.defaultdict(list)
for c in corpus: by_repo[norm(c["url"])].append(c)
# ---------- exclusions ----------
hold_urls = open(os.path.join(ROOT, "eval/hancore_holdout/plugin_ids.txt")).read().split()
ex_repos = {norm(u) for u in hold_urls}; ex_ids = set(); ex_fps = []   # fps: (label, set)
real_of = {norm(u): common.repo_of(u) for u in hold_urls}
hold_commit = {norm(json.loads(l)["plugin"]): json.loads(l)["commit"] for l in open(os.path.join(ROOT, "eval/hancore_holdout/manifest.jsonl"))}
def manifest_id(files):
    for k, v in files.items():
        if k == "manifest.json" or k.endswith("/manifest.json") and k.count("/") <= 1:
            try: return json.loads(v).get("id")
            except Exception: pass
for r, sha in hold_commit.items():
    d = os.path.join(CACHE, real_of[r].replace("/", "__") + "@" + sha)
    if os.path.isdir(d):
        f = read_dir(d); ex_fps.append(("holdout:" + r, fp_dir(f))); mid = manifest_id(f)
        if mid: ex_ids.add(mid.lower())
    for c in by_repo.get(r, []): ex_ids.add((c.get("plugin_id") or "").lower())
n_key = 0
for l in open(os.path.join(ROOT, "functest/dell_ground_truth.jsonl")):   # only id/source/path are touched
    g = json.loads(l); n_key += 1; ex_ids.add(g["id"].lower())
    for base in (ROOT, "/workspace/omarchy-specialist"):
        d = os.path.join(base, g["path"])
        if os.path.isdir(d):
            f = read_dir(d); ex_fps.append(("dellkey:" + g["id"], fp_dir(f))); mid = manifest_id(f)
            if mid: ex_ids.add(mid.lower())
            break
    for c in corpus:
        if (c.get("plugin_id") or "").lower() == g["id"].lower() or (c.get("dell_name") or "") == g["id"]: ex_repos.add(norm(c["url"]))
ex_ids.discard("")
def near_dup(fp):
    if len(fp) < 2: return None
    for lab, s in ex_fps:
        if not s: continue
        j = len(fp & s) / len(fp | s)
        if j >= 0.6: return lab
    return None
# ---------- source access ----------
def source_for(repo, sha, real=None):
    """-> (files dict, origin) at exactly sha, or (None, reason)."""
    d = os.path.join(CACHE, (real or repo).replace("/", "__") + "@" + sha)
    files = {}
    if os.path.exists(d + "/.ok"): files = read_dir(d); origin = "hancore_cache"
    else: origin = None
    for c in by_repo.get(repo, []):
        ld = c.get("local_dir")
        if not ld or not os.path.isdir(ld): continue
        if c["commit"] == sha:
            for k, v in read_dir(ld).items(): files.setdefault(k, v)
            origin = (origin or "") + "+local_dir"
        elif os.path.isdir(ld + "/.git"):
            try:
                ls = subprocess.run(["git", "-C", ld, "ls-tree", "-r", "--name-only", sha], capture_output=True, text=True, timeout=30)
                if ls.returncode == 0:
                    for p in ls.stdout.splitlines():
                        if p in files or p.startswith(".git"): continue
                        b = subprocess.run(["git", "-C", ld, "show", f"{sha}:{p}"], capture_output=True, timeout=30).stdout
                        if len(b) < 400_000:
                            try: files[p] = b.decode("utf-8")
                            except Exception: pass
                    origin = (origin or "") + "+git"
            except Exception: pass
    return (files, origin) if files else (None, "no_source_at_commit")
FULL = OUT + "/src_full"
def full_fetch(real, sha):
    """Whole-tree text files at the exact commit via GitHub tarball (public read) into a NEW cache; returns dict or None."""
    d = os.path.join(FULL, real.replace("/", "__") + "@" + sha)
    if os.path.exists(d + "/.fail"): return None
    if not os.path.exists(d + "/.ok"):
        os.makedirs(d, exist_ok=True)
        try:
            r = subprocess.run(["gh", "api", f"repos/{real}/tarball/{sha}"], capture_output=True, timeout=120)
            t = tarfile.open(fileobj=io.BytesIO(r.stdout), mode="r:gz")
            for m in t.getmembers():
                if not m.isfile() or m.size > 400_000: continue
                rel = m.name.split("/", 1)[1] if "/" in m.name else m.name
                if rel.startswith(".git/") or "/node_modules/" in "/" + rel: continue
                b = t.extractfile(m).read()
                try: b.decode("utf-8")
                except UnicodeDecodeError: continue
                rel = posixpath.normpath(rel)
                if rel.startswith(("/", "..")) or "\0" in rel: continue   # zip-slip guard (audit C3)
                pth = os.path.join(d, rel)
                if not os.path.realpath(pth).startswith(os.path.realpath(d) + os.sep): continue
                os.makedirs(os.path.dirname(pth), exist_ok=True); open(pth, "wb").write(b)
            open(d + "/.ok", "w").write("1")
        except Exception as e:
            open(d + "/.fail", "w").write(repr(e)[:200]); return None
    return read_dir(d)
# ---------- parsing ----------
EXT = r"qml|sh|bash|py|js|mjs|lua|json|md|conf|toml|ya?ml|html|txt|desktop|service|ini|ts|rs|go|css|jsonc|cpp|hpp|c|h|rules|zsh|fish"
FILE_RE = re.compile(r"(?<![\w/.-])((?:[\w.@+-]+/)*[\w.@+-]+\.(?:%s))(?![\w])(?:\s*[:#L]{1,2}\s*(\d+)(?:\s*[–\-—]\s*L?(\d+))?)?" % EXT)
EXTLESS = re.compile(r"`((?:[\w.-]+/)+[\w-]+)(?::(\d+)(?:[–\-](\d+))?)?`")
BARE = re.compile(r"(?<![\w/.:-])((?:bin|scripts?|lib|libexec|hooks?|src|helpers?|tools?|share|data|contrib)/[\w.-]+(?:/[\w.-]+)*)(?![\w/.])(?:\s*:\s*(\d+)(?:\s*[–\-—]\s*(\d+))?)?")
LINE_NEAR = re.compile(r"(?i)\blines?\s+(\d+)(?:\s*[–\-—]\s*(\d+))?")
TICK = re.compile(r"`([^`\n]{4,120})`")
HEX = re.compile(r"^[0-9a-f]{7,40}$")
def parse(text):
    refs = []; seen = set()
    for m in list(FILE_RE.finditer(text)) + list(EXTLESS.finditer(text)) + list(BARE.finditer(text)):
        f = m.group(1)
        if f.startswith(("http", "www.")) or "github.com" in f or f.lower() in ("e.g", "i.e"): continue
        pre = text[max(0, m.start() - 12):m.start()]
        if "://" in pre or "/" in pre[-1:] and "." in f and not "/" in f: continue
        ln = int(m.group(2)) if m.group(2) else None
        ln2 = int(m.group(3)) if m.lastindex and m.lastindex >= 3 and m.group(3) else None
        if ln is None:  # "file.sh (lines 12-20)" / "file.sh, line 12"
            nm = LINE_NEAR.match(text[m.end():m.end() + 30].lstrip(" ,(:"))
            if nm: ln = int(nm.group(1)); ln2 = int(nm.group(2)) if nm.group(2) else None
        key = (f, ln)
        if key in seen: continue
        seen.add(key); refs.append(dict(file=f, line=ln, line_end=ln2, pos=m.start()))
    return refs
def tokens(text, ref_file):
    t = []
    for m in TICK.finditer(text):
        s = m.group(1).strip()
        if HEX.match(s) or FILE_RE.fullmatch(s) or s == ref_file or len(s) < 4: continue
        if re.fullmatch(r"[\w./-]+:\d+(?:[–-]\d+)?", s): continue
        if re.fullmatch(r"(?:https?://\S+|[A-Za-z]+)", s) and len(s) < 5: continue
        t.append(s)
    return list(dict.fromkeys(t))
def ws(s): return re.sub(r"\s+", " ", s)
PROSE_KIND = [("secrets-credentials", r"process (?:argument|argv|list|command line)|command[- ]line|\bargv\b|procfs|token|credential|passcode|password|secret"),
 ("shell-lua-injection", r"inject|interpret(?:ed|s)? (?:as|it)|-delete|sh -c|bash -c|\beval\b|option inject|unescaped|unquoted"),
 ("file-safety-symlink-perms", r"symlink|predictable|/tmp|mktemp|chmod|permission|race|toctou|FIFO|no-follow"),
 ("unbounded-input-resource", r"unbounded|size limit|exhaust|memory|oversized|without a (?:size|timeout|deadline)"),
 ("rich-text-markup-injection", r"PlainText|rich text|StyledText|AutoText|textFormat"),
 ("privileged-system", r"\bsudo\b|pkexec|polkit|\broot\b|setuid"),
 ("remote-code-pinning", r"unpinned|curl[^.]{0,30}\|\s*(?:ba)?sh|checksum|mutable ref"),
 ("url-scheme-network", r"xdg-open|URL scheme|http://|TLS|redirect"),
 ("process-lifecycle-timeouts", r"timeout|orphan|zombie|leak|hang|stall|kill"),
 ("install-deps-packaging", r"missing dependenc|not installed|pacman|PKGBUILD"),
 ("user-config-modification", r"overwrit|clobber|backup|user config|keybind")]
def kind_for(cats, text, pos):
    c = [x for x in cats if x in K13]
    if not c:
        win = text[max(0, pos - 350):pos + 450]; best = None
        for k, rx in PROSE_KIND:
            n = len(re.findall(rx, win, re.I))
            if n and (best is None or n > best[0]): best = (n, k)
        return best[1] if best else None
    if len(c) == 1: return c[0]
    win = text[max(0, pos - 350):pos + 450]
    sc = {k: sum(1 for _, rx in KINDS.get(k, []) if re.search(rx, win, re.I)) for k in c}
    return max(c, key=lambda k: (sc[k], -c.index(k)))
def subkind(cat, text):
    for k, rx in KINDS.get(cat, []):
        if re.search(rx, text, re.I): return k
    return None
def resolve(files, f):
    f = f.lstrip("./")
    if f in files: return f
    c = [k for k in files if k.endswith("/" + f)]
    if len(c) == 1: return c[0]
    if "/" not in f:
        c = [k for k in files if os.path.basename(k) == f]
        if len(c) == 1: return c[0]
        if len(c) > 1: return "AMBIG"
    return None
def scrub(s):
    s = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+\b", "<email>", s); s = re.sub(r"/home/[\w.-]+", "/home/user", s)
    return re.sub(r"(?<![\w/])@([A-Za-z0-9-]{2,39})\b(?![./])", "@user", s)
def verify_ref(files, ref, toks, cats_kind, text):
    """-> (status, reason, detail)"""
    p = resolve(files, ref["file"])
    if p is None: return "fail", "file_missing_at_commit", None
    if p == "AMBIG": return "fail", "file_ambiguous", None
    lines = files[p].split("\n"); n = len(lines); ln = ref["line"]
    lo, hi = (ln, ref["line_end"] or ln) if ln else (None, None)
    if ln:
        if ln < 1 or ln > n: return "fail", "line_out_of_range", dict(path=p, n=n)
        a, b = max(0, lo - 1 - 12), min(n, max(hi, lo) + 12); win = ws("\n".join(lines[a:b]))
        for t in toks:
            if ws(t) in win: return "ok", "quoted_code_near_line", dict(path=p, tok=t[:60])
        # identifiers inside tokens, e.g. fn() -> fn
        for t in toks:
            for idn in re.findall(r"[A-Za-z_][\w.]{4,}", t):
                if idn in win and len(idn) >= 6: return "ok", "identifier_near_line", dict(path=p, tok=idn)
        if toks:
            allf = ws(files[p])
            if any(ws(t) in allf for t in toks): return "fail", "construct_in_file_but_not_near_line", dict(path=p)
        rx = [r for _, r in KINDS.get(cats_kind, [])]
        if rx and any(re.search(r, "\n".join(lines[a:b]), re.I) for r in [r for r in rx][:0] + [x for x in CONSTRUCT.get(cats_kind, [])]):
            return "ok", "category_construct_near_line", dict(path=p)
        return "fail", "line_ok_no_construct_match", dict(path=p)
    # no line
    allf = ws(files[p])
    for t in toks:
        if ws(t) in allf:
            i = allf.find(ws(t)); return "ok_noline", "quoted_code_in_file", dict(path=p, tok=t[:60])
    return "fail", "file_ok_no_line_no_construct", dict(path=p)
# category construct regexes over code (not prose)
CONSTRUCT = {
 "install-deps-packaging": [r"pacman|yay|paru|pip |npm |apt|command -v|which |install|PKGBUILD|requires|depends|dependenc"],
 "unbounded-input-resource": [r"curl|wget|XMLHttpRequest|urlopen|requests\.|\.read\(|cat |readFile|FileView|StdioCollector|head -c|max-filesize|while read|JSON\.parse"],
 "file-safety-symlink-perms": [r"/tmp|mktemp|chmod|umask|ln -s|symlink|O_NOFOLLOW|open\(|rm -|mv |cp |>\s*[\"$~/]|tee |Path\(|os\.replace|rename|mkdir"],
 "secrets-credentials": [r"token|secret|password|passwd|api[_-]?key|credential|auth|bearer|keyring|0600"],
 "privileged-system": [r"sudo|pkexec|polkit|/etc/|/usr/|systemctl|udev|modprobe|/dev/|setcap|root"],
 "process-lifecycle-timeouts": [r"Process|Timer|timeout|sleep|while |kill|trap|&\s*$|nohup|setsid|interval|running|exec|spawn|Popen|subprocess|flock"],
 "remote-code-pinning": [r"curl|wget|git clone|git pull|pip install|npm|cargo|yay|paru|raw\.githubusercontent|releases/latest|@latest|checksum|sha256|\| *(?:ba)?sh"],
 "url-scheme-network": [r"https?://|openUrlExternally|xdg-open|curl|wget|XMLHttpRequest|urlopen|fetch|socket|--insecure|-k |verify"],
 "rich-text-markup-injection": [r"textFormat|Text\.|RichText|StyledText|AutoText|Markdown|notify|\btext:|\.text\b|<[a-z]+>"],
 "listing-metadata-docs": [r"\"id\"|\"name\"|version|license|description|README|preview|entryPoints|kinds|category"],
 "user-config-modification": [r"\.config|hypr|\.bashrc|\.zshrc|bindings|keybind|>>|sed -i|write|FileView|setText|config"],
 "shell-lua-injection": [r"sh -c|bash -c|eval|exec|hyprctl|dispatch|command:|Process|os\.execute|\$\(|`|system\(|Popen|subprocess|\[\s*\"(?:ba)?sh\""],
 "runtime-qml-api-compat": [r"import |Quickshell|Qt|QtQuick|property |signal |Component|Loader|Connections|\bid:"],
}
def main():
    D = common.load(); counts = collections.Counter(); rows = []; fails = collections.Counter(); excl = collections.Counter(); fail_samples = collections.defaultdict(list)
    file_only = []; kind_stat = collections.defaultdict(collections.Counter); src_cache = {}; excl_plugins = {}
    plug_ok = {}
    for p, v in sorted(D.items()):
        if not v["sha"]: continue
        gt = [x for x in v["gt"] if common.strength(x["fixed"]) in ("strong", "likely")]
        if not gt: continue
        repo = norm(p)
        if p in set(hold_urls) or repo in ex_repos: why = "holdout_or_dellkey_repo"
        else:
            why = None
        if why is None:
            ids = {(c.get("plugin_id") or "").lower() for c in by_repo.get(repo, [])}
            if ids & ex_ids: why = "manifest_id_match"
        files = None; origin = None
        if why is None:
            files, origin = source_for(repo, v["sha"], common.repo_of(p))
            if files:
                mid = (manifest_id(files) or "").lower()
                if mid and mid in ex_ids: why = "manifest_id_match"
                else:
                    nd = near_dup(fp_dir(files))
                    if nd: why = "near_duplicate_tree:" + nd.split(":")[0]
        if why:
            excl[why] += len(gt); excl_plugins[p] = why
            if why.startswith("near"): counts["excluded_plugins_near_dup"] += 1
            if why.startswith("holdout") and p not in set(hold_urls): counts["excluded_plugins_repo_match_extra"] += 1
            continue
        got_full = False
        for x in gt:
            counts["findings_considered"] += 1
            text = x["text"]; cats = x["categories"]
            base = dict(plugin=repo, plugin_url=p, commit=v["sha"], outcome=x["fixed"], strength=common.strength(x["fixed"]), comment_url=x["url"],
                        fix_evidence_url=x["fixed_evidence_url"], hancore_categories=cats)
            def fail(reason, sample=None):
                fails[reason] += 1; counts["failed"] += 1
                if len(fail_samples[reason]) < 6: fail_samples[reason].append(dict(url=x["url"], cats=cats, text=text[:400]))
            if files is None: fail("no_source_at_commit"); continue
            if CLEAN_RE.search(text) and not re.search(r"(?i)blocker[s]? (?:found|:)|must|please|should|fix", text): fail("parse:clean_or_approval_prose"); continue
            refs = parse(text)
            if not refs: fail("parse:no_file_reference"); continue
            kind0 = kind_for(cats, text, refs[0]["pos"])
            if kind0 is None: fail("parse:no_bug_kind_in_13"); continue
            counts["parsed"] += 1
            best = None
            for r in refs[:8]:
                k = kind_for(cats, text, r["pos"]) or kind0
                nxt = min([q["pos"] for q in refs if q["pos"] > r["pos"]] + [len(text)])
                toks = tokens(text[max(0, r["pos"] - 300):nxt + 250], r["file"]) or tokens(text, r["file"])
                st, why_, det = verify_ref(files, r, toks, k, text)
                if why_ == "file_missing_at_commit" and not got_full:
                    got_full = True; ff = full_fetch(common.repo_of(p), v["sha"]); counts["full_fetches"] += 1
                    if ff:
                        files = dict(ff, **files); origin = (origin or "") + "+gh_tarball"
                        st, why_, det = verify_ref(files, r, toks, k, text)
                cand = (st, why_, det, r, k)
                if st in ("ok", "ok_noline"):
                    if best is None or best[0] != "ok" and st == "ok": best = cand
                    if st == "ok": break
                elif best is None or best[0] == "fail" and why_ in ("line_ok_no_construct_match",) and best[1] not in ("line_ok_no_construct_match",): best = cand
            st, why_, det, r, k = best
            if st == "fail":
                if why_ == "file_ok_no_line_no_construct":   # file-level only: separate, lower-confidence tier
                    file_only.append(dict(base, file=det["path"], line=None, line_end=None, bug_kind=k, sub_kind=subkind(k, text), verify="file_exists_only", source_origin=origin, n_refs=len(refs), prose=scrub(ws(text[:330]))))
                fail("verify:" + why_); continue
            counts["verified"] += 1
            pos = r["pos"]; a = max(text.rfind(". ", 0, pos), text.rfind("\n", 0, pos)); a = 0 if a < 0 else a + 1
            prose = scrub(ws(text[a:a + 330])).strip()
            row = dict(base, file=det["path"], line=r["line"], line_end=r["line_end"], bug_kind=k, sub_kind=subkind(k, text),
                       verify=why_, confidence=("high" if why_ in ("quoted_code_near_line", "identifier_near_line") else "medium" if why_ == "quoted_code_in_file" else "low"), source_origin=origin, n_refs=len(refs), prose=prose)
            rows.append(row)
            ks = kind_stat[k]; ks["verified"] += 1; ks["with_line"] += 1 if r["line"] else 0
            ks["strong"] += row["strength"] == "strong"; ks["with_fix_url"] += 1 if row["fix_evidence_url"] else 0
    os.makedirs(OUT, exist_ok=True)
    with open(OUT + "/concrete_findings.jsonl", "w") as f:
        for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(OUT + "/file_level_only.jsonl", "w") as f:
        for r in file_only: f.write(json.dumps(r, ensure_ascii=False) + "\n")
    fo = collections.Counter(r["bug_kind"] for r in file_only)
    summary = dict(counts=dict(counts), failures=dict(fails.most_common()), excluded_findings=dict(excl), excluded_plugins=len(excl_plugins),
                   exclusion_inputs=dict(holdout_repos=len(hold_urls), dell_key_rows=n_key, ex_ids=len(ex_ids), ex_repos=len(ex_repos), fingerprints=len(ex_fps)),
                   per_kind={k: dict(v, share_with_line=round(v["with_line"] / v["verified"], 3)) for k, v in sorted(kind_stat.items(), key=lambda kv: -kv[1]["verified"])},
                   fail_samples=fail_samples, file_level_only=dict(total=len(file_only), per_kind=dict(fo)))
    json.dump(summary, open(OUT + "/summary.json", "w"), indent=1, ensure_ascii=False)
    json.dump(excl_plugins, open(OUT + "/excluded_plugins.json", "w"), indent=0)
    print(json.dumps({k: v for k, v in summary.items() if k != "fail_samples"}, indent=1))
if __name__ == "__main__": main()
