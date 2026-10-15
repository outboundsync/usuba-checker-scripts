#!/usr/bin/env python3
"""Turn the Dell hit-check JSONL into tables.
usage: python3 analyze_results.py hitcheck-results.jsonl [--jobs jobs.json] [--md out.md] [--csv-prefix out/hc]
Batch A, per rule (claims of group rule_sample): n, works, broken, unsure, and how observable the rule's defect was on hardware:
  direct   = the defect pattern itself was seen at runtime (e.g. curl called without a byte cap, a fixed /tmp file created, sudo invoked, 'Required property' load failure)
  executed = the flagged code ran (script/command seen) but the defective behaviour itself is not visible from the outside (e.g. an unbounded python read)
  static   = only the flagged file/code exists (e.g. AGENTS.md shipped, hardcoded literal); nothing at runtime shows it
  none     = no evidence either way
Skip cases (group skip_case: the old rule fired, the v3-fixes skip conditions suppress it) are listed separately; 'direct' there means the skip rule hid a real defect.
Batch B, per pair: pre-fix broken?, pre-fix differs (new warning/ipc/process signature vs post-fix)?, post-fix works?, confirmed = (pre broken or differs) and post works."""
import json, sys, re, os, collections, argparse, csv
ap = argparse.ArgumentParser(); ap.add_argument("jsonl"); ap.add_argument("--jobs"); ap.add_argument("--md"); ap.add_argument("--csv-prefix"); a = ap.parse_args()
recs = {}
for l in open(a.jsonl):
    l = l.strip()
    if not l: continue
    try: r = json.loads(l)
    except Exception: continue
    recs[r["job"]] = r        # last line wins (re-runs)
jobs = None
if a.jobs and os.path.exists(a.jobs): jobs = json.load(open(a.jobs))["jobs"]
else:
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jobs.json")
    if os.path.exists(p): jobs = json.load(open(p))["jobs"]
if jobs is None: jobs = [r["meta"] for r in recs.values() if r.get("meta")]
base = os.path.basename
def argv_all(r): return [" ".join(c) for c in r.get("shim_calls", [])] + list(r.get("child_cmds", []))
def shim(r, *tools): return [c for c in r.get("shim_calls", []) if c and base(c[0]) in tools]
def toks(sn): return [t for t in re.findall(r"[\"']([^\"'\n]{12,})[\"']", sn or "") if not re.match(r"^[\w./-]*$", t) or len(t) >= 20]
def ran(r, c):
    b = base(c["file"]); return any(b in x for x in argv_all(r)) or any(b in x for x in r.get("log_lines", []))
AUTH = re.compile(r"authorization|bearer|x-api-key|api[-_]?key|--oauth2-bearer", re.I)
SECRET_ARGV = re.compile(r"[?&](api[_-]?key|key|token|access_token|secret|password|passwd|auth)=\S+|--(password|token|api-key|secret)\b|authorization:|bearer\s+\S+|\s-u\s+\S+:\S+", re.I)
def obs(rule, r, c):
    A = argv_all(r); cur = shim(r, "curl", "wget"); X = ran(r, c)
    cmd_curl = [x for x in r.get("child_cmds", []) if re.match(r"(/\S*/)?(curl|wget)\b", x)]
    if rule == "USB-HC01":
        if any("--max-filesize" not in " ".join(x) for x in cur) or any("--max-filesize" not in x for x in cmd_curl): return "direct"
    elif rule == "USB-HC02":
        if any(re.search(r"python", x) and base(c["file"]) in x for x in A): return "executed"
    elif rule == "USB-HC04":
        ents = [e for e in r.get("tmp_entries", []) if "/" not in e["path"]]
        if any(not re.match(r"^(tmp\.|\.?[A-Za-z0-9_-]*\.[A-Za-z0-9]{6,}$|tmp[A-Za-z0-9_]{6,}$)", e["path"]) for e in ents): return "direct"
    elif rule == "USB-HC05":
        if any(e["type"] in "fd" and len(e["mode"]) >= 3 and int(e["mode"][-1]) & 2 for e in r.get("tmp_entries", []) + r.get("files_written", [])): return "direct"
    elif rule == "USB-HC08":
        if any(t in x for t in toks(c.get("snippet")) for x in A): return "direct"
        if X: return "executed"
    elif rule == "USB-HC09":
        if any(SECRET_ARGV.search(x) for x in A): return "direct"
    elif rule == "USB-HC10":
        if any(re.search(r"http://(?!localhost|127\.|\[::1\]|0\.0\.0\.0)", x) or re.search(r"\s(-k|--insecure)\b", x) for x in A): return "direct"
    elif rule == "USB-HC15":
        if shim(r, "sudo", "pkexec", "doas", "su") or any(re.search(r"(^|\s|/)(sudo|pkexec|doas)\s", x) for x in A): return "direct"
    elif rule == "USB-HC16":
        if c.get("file_present"): return "static"
    elif rule == "USB-HC17":
        if shim(r, "pip", "pip3", "pipx", "npm", "npx", "pnpm", "yarn", "bun", "uv", "uvx", "cargo", "go", "yay", "paru") or [x for x in shim(r, "git") if x[1:2] == ["clone"]] or any(re.search(r"(curl|wget)[^|]*\|\s*(ba)?sh", x) for x in A): return "direct"
    elif rule == "USB-HC19":
        if [x for x in shim(r, "pip", "pip3", "pipx", "uv", "uvx") if "install" in x or "run" in x] and not any("--require-hashes" in " ".join(x) for x in shim(r, "pip", "pip3", "pipx", "uv")): return "direct"
    elif rule == "USB-HC20":
        if any(AUTH.search(" ".join(x)) and re.search(r"(^|\s)(-L|--location)\b", " ".join(x)) for x in cur): return "direct"
        if any(re.search(r"python", x) and base(c["file"]) in x for x in A): return "executed"
    elif rule == "USB-HC25":
        if any(AUTH.search(" ".join(x)) and "--max-redirs 0" not in " ".join(x) for x in cur): return "direct"
    elif rule == "USB-L02":
        if r.get("extra_quickshell") or any("ShellRoot" in e for e in r.get("qml_fatal", []) + r.get("qml_warnings", [])): return "direct"
        if r.get("listed"): return "executed"
    elif rule == "USB-L03":
        if any("Required property" in e for e in r.get("qml_fatal", []) + r.get("qml_warnings", [])): return "direct"
    elif rule in ("USB-N01", "USB-N02"):
        if r.get("listed") is False or r.get("enabled") is False or r.get("verdict") == "broken" or any("manifest" in e.lower() or "PluginRegistry" in e for e in r.get("log_lines", [])): return "direct"
    if X and rule not in ("USB-HC16",): return "executed"
    return "none"
rows = []; missing = []
jb = {j["job"]: j for j in jobs}
for j in jobs:
    if j["batch"] != "A": continue
    r = recs.get(j["job"])
    if not r: missing.append(j["job"]); continue
    for c in j.get("claims", []):
        rows.append(dict(rule=c["rule"], group=c["group"], job=j["job"], repo=j["repo"], verdict=r["verdict"], obs=(obs(c["rule"], r, c) if c["rule"] else "none"), error=r.get("error"), file=c["file"], line=c["line"], origin=c.get("origin"), fires_now=c.get("fires_now")))
out = []
def table(title, head, body): out.append(f"\n### {title}\n\n| " + " | ".join(head) + " |\n|" + "---|" * len(head)); out.extend("| " + " | ".join(str(x) for x in b) + " |" for b in body)
def summarize(group):
    by = collections.defaultdict(list)
    for x in rows:
        if x["group"] == group: by[x["rule"]].append(x)
    body = []
    for rule in sorted(by):
        L = by[rule]; n = len(L); v = collections.Counter(x["verdict"] for x in L); o = collections.Counter(x["obs"] for x in L)
        body.append([rule, n, v["works"], v["broken"], v["unsure"], o["direct"], o["executed"], o["static"], o["none"], f"{(o['direct'])}/{n}"])
    return body
H = ["rule", "n", "works", "broken", "unsure", "defect direct", "executed only", "static only", "none", "direct rate"]
out.append(f"# Dell hit-check result table\n\nresult lines: {len(recs)}; jobs in package: {len(jobs)}; jobs without a result: {len(missing)}")
tA = summarize("rule_sample"); table("Batch A: enabled rules (plugins whose current-code hit was sampled)", H, tA)
tS = summarize("skip_case")
if tS: table("Batch A: skip-rule cases (old rule fired, v3-fixes skip conditions suppress it; 'direct' would mean the skip hid a real defect)", H, tS)
tC = [[x["job"], x["verdict"], x["error"] or ""] for x in rows if x["group"] == "clean_control"]
if tC: table("Batch A: clean controls (should load and show no defect)", ["job", "verdict", "error"], tC)
broken = [x for x in rows if x["group"] == "rule_sample" and x["verdict"] == "broken"]
if broken: table("Batch A: broken plugins in rule samples (first error)", ["rule", "plugin job", "error"], [[x["rule"], x["job"], (x["error"] or "")[:150]] for x in broken][:60])
# ---- B
pairs = collections.defaultdict(dict)
for j in jobs:
    if j["batch"] == "B": pairs[j["pair"]][j["side"]] = j
pb = []; sums = collections.Counter(); bykind = collections.defaultdict(collections.Counter)
for p, sd in sorted(pairs.items()):
    pre, post = recs.get(sd["pre"]["job"]) if "pre" in sd else None, recs.get(sd["post"]["job"]) if "post" in sd else None
    if not pre or not post: missing += [sd[s]["job"] for s in sd if not recs.get(sd[s]["job"])]; continue
    d_sig = sorted(set(pre.get("signature", [])) - set(post.get("signature", [])))
    d_ipc = {k: v for k, v in pre.get("ipc_out", {}).items() if post.get("ipc_out", {}).get(k) != v}
    d_cmd = sorted({re.sub(r"\d+", "N", x) for x in pre.get("child_cmds", [])} ^ {re.sub(r"\d+", "N", x) for x in post.get("child_cmds", [])})
    differs = bool(d_sig or d_ipc or d_cmd or pre.get("listed") != post.get("listed") or pre.get("toggle_ok") != post.get("toggle_ok"))
    pre_broken = pre["verdict"] == "broken"; post_works = post["verdict"] == "works"; conf = (pre_broken or differs) and post_works
    kind = sd["pre"]["bug_kind"]; sums["pairs"] += 1; sums["pre_broken"] += pre_broken; sums["pre_differs"] += differs; sums["post_works"] += post_works; sums["confirmed"] += conf; sums["pre_broken_post_works"] += (pre_broken and post_works)
    bykind[kind]["n"] += 1; bykind[kind]["pre_broken"] += pre_broken; bykind[kind]["differs"] += differs; bykind[kind]["post_works"] += post_works; bykind[kind]["confirmed"] += conf
    why = (pre.get("error") or (d_sig[0][:100] if d_sig else "") or (("ipc " + next(iter(d_ipc))) if d_ipc else "") or ("process set differs" if d_cmd else ""))
    pb.append([p, kind, sd["pre"]["file"], "yes" if pre_broken else "no", "yes" if differs else "no", pre["verdict"], post["verdict"], "yes" if post_works else "no", "YES" if conf else "no", why[:110]])
table("Batch B: version-history pairs", ["pair", "bug kind", "file", "pre-fix broken?", "pre-fix differs?", "pre verdict", "post verdict", "post-fix works?", "confirmed", "evidence"], pb)
if sums["pairs"]:
    table("Batch B: totals", ["pairs", "pre-fix broken", "pre-fix differs", "pre broken and post works", "post-fix works", "confirmed"], [[sums["pairs"], sums["pre_broken"], sums["pre_differs"], sums["pre_broken_post_works"], sums["post_works"], sums["confirmed"]]])
    table("Batch B: by bug kind", ["bug kind", "pairs", "pre-fix broken", "pre-fix differs", "post-fix works", "confirmed"], [[k, v["n"], v["pre_broken"], v["differs"], v["post_works"], v["confirmed"]] for k, v in sorted(bykind.items())])
if missing: out.append("\nMissing results: " + ", ".join(sorted(set(missing))[:40]) + (" ..." if len(set(missing)) > 40 else ""))
txt = "\n".join(out) + "\n"
print(txt)
if a.md: open(a.md, "w").write(txt)
if a.csv_prefix:
    os.makedirs(os.path.dirname(a.csv_prefix) or ".", exist_ok=True)
    with open(a.csv_prefix + "_A_claims.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["rule"]); w.writeheader(); [w.writerow(x) for x in rows]
    with open(a.csv_prefix + "_B_pairs.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["pair", "bug_kind", "file", "pre_broken", "pre_differs", "pre_verdict", "post_verdict", "post_works", "confirmed", "evidence"]); [w.writerow(x) for x in pb]
