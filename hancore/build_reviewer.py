#!/usr/bin/env python3
"""Build (plugin code + Checker report) -> HANCORE-style finding list examples. NOT used for training yet.
Non-holdout plugins only. Secrets / emails / handles / home paths scrubbed. Output: data/hancore_reviewer/examples.jsonl.gz + stats.json"""
import sys, os, re, json, gzip, collections, signal
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H); sys.path.insert(0, os.path.join(H, "../functest"))
import common, fetch
from usuba import hancore_rules as HR, checks
OUT = os.path.join(H, "../data/hancore_reviewer")
HOLD = set(open(os.path.join(H, "../eval/hancore_holdout/plugin_ids.txt")).read().split())
CODE_CAP, FILE_CAP = 24000, 8000
WEIGHT = {"strong": 1.0, "likely": 0.6, "open": 0.3, "closed_no_fix": 0.2, "stale": 0.15, "not_planned": 0.1}
SEC = [re.compile(p) for p, _ in HR.SECRET_PATS[:7]] + [re.compile(r"(?i)((?:api[_-]?key|secret|token|password|passwd)\w*\s*[:=]\s*[\"'`])([A-Za-z0-9_\-+/=.]{16,})([\"'`])")]
def scrub(s, handles=()):
    for i, r in enumerate(SEC):
        s = r.sub((lambda m: m.group(1) + "<REDACTED>" + m.group(3)) if i == len(SEC) - 1 else "<REDACTED_SECRET>", s)
    s = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+\b", lambda m: m.group(0) if m.group(0).endswith(("noreply.github.com",)) and False else "<email>", s)
    s = re.sub(r"/home/[\w.-]+", "/home/user", s)
    s = re.sub(r"(?<![\w/])@([A-Za-z0-9-]{2,39})\b(?![./])", lambda m: m.group(0) if m.group(1) in ("param", "returns", "media", "import", "keyframes") else "@user", s)
    return s
def order(p):
    return (0 if p == "manifest.json" else 1 if p.endswith((".qml", ".js", ".sh", ".py", ".lua", ".bash")) else 2 if p.lower().startswith("readme") else 3, p)
def code_blob(files):
    out, n = [], 0
    for p in sorted(files, key=order):
        c = files[p][:FILE_CAP]
        if n + len(c) > CODE_CAP: out.append(f"### {p}\n(omitted: {len(files[p])} chars)"); continue
        out.append(f"### {p}\n```\n{c}\n```"); n += len(c)
    return "\n\n".join(out)
class TO(Exception): pass
def _alarm(*a): raise TO()
signal.signal(signal.SIGALRM, _alarm)
def report(files):
    try:
        signal.alarm(20); fs = checks.check(files); signal.alarm(0)
        rep = [checks.fmt(f) for f in fs]
    except Exception as e:
        signal.alarm(0); rep = None
    rep2 = [f"[{f['rule']} warn{' experimental' if f['rule'] in HR.EXPERIMENTAL else ''}] {f['file']}: {f['reason']}" for f in HR.check(files, experimental=True) if f["rule"] in HR.EXPERIMENTAL]
    return (rep or []) + rep2 if rep is not None else None
d = common.load(); rows = []; st = collections.Counter(); fs_st = collections.Counter(); cats = collections.Counter()
with gzip.open(os.path.join(OUT, "examples.jsonl.gz"), "wt") as fo:
    for p, v in sorted(d.items()):
        if p in HOLD or not v["sha"] or not v["gt"]: continue
        st["plugins_with_findings"] += 1
        src = os.path.join(fetch.CACHE, common.repo_of(p).replace("/", "__") + "@" + v["sha"])
        if not os.path.exists(src + "/.ok"): st["no_code"] += 1; continue
        files = fetch.read_files(src)
        if not files: st["empty_code"] += 1; continue
        rep = report(files)
        fl = []
        for x in v["gt"]:
            s = common.strength(x["fixed"]); fs_st[s] += 1
            for c in x["categories"]: cats[c] += 1
            sevm = re.search(r"\b(Critical|High|Medium|Low|P[0-3])\b", x["text"][:200])
            fl.append(dict(severity=sevm.group(1) if sevm else None, categories=x["categories"], finding=scrub(x["text"][:4000]), strength=s, outcome=x["fixed"],
                           provenance=dict(comment_url=x["url"], thread=x["thread"], fix_evidence_url=x["fixed_evidence_url"], date=x["date"])))
        best = min((f["strength"] for f in fl), key=lambda s: -WEIGHT[s])
        ex = dict(id=f"{common.repo_of(p)}@{v['sha'][:12]}", plugin=p, repo=common.repo_of(p), commit=v["sha"],
                  threads=sorted({x["thread"] for x in v["gt"]}), strength=best, weight=WEIGHT[best],
                  weak_label=best in ("closed_no_fix", "stale", "not_planned"),
                  input=dict(code=scrub(code_blob(files)), checker_report=[scrub(r) for r in rep] if rep is not None else None, n_files=len(files)),
                  target=dict(findings=fl))
        fo.write(json.dumps(ex) + "\n"); st["examples"] += 1; st["strength:" + best] += 1
        if rep is None: st["checker_report_unavailable"] += 1
stats = dict(examples=st["examples"], plugins_with_findings_nonholdout=st["plugins_with_findings"], skipped_no_code=st["no_code"] + st["empty_code"],
             checker_report_unavailable=st["checker_report_unavailable"],
             examples_by_strength={k[9:]: v for k, v in st.items() if k.startswith("strength:")}, findings_by_strength=dict(fs_st), findings_by_category=dict(cats.most_common()),
             weights=WEIGHT, holdout_excluded=len(HOLD))
json.dump(stats, open(os.path.join(OUT, "stats.json"), "w"), indent=1); print(json.dumps(stats, indent=1))
