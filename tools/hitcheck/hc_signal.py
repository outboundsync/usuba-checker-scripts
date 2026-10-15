#!/usr/bin/env python3
"""Turn one finished run directory (raw/<job>/) into ONE JSON line (stdout). Load verdict rule = DELL_LEARNINGS.md section 2 (class based, same FATAL regex as
dell/sweep/build_results.py): a QML message fails a plugin only when it stops a component from being created; shell death, not listed/registered, a failing
toggle on a panel/overlay/menu, or runaway memory also fail it. Everything else is a warning. Evidence fields (shim_calls, child_cmds, tmp_entries,
files_written, ipc_out, log_lines) feed analyze_results.py.   usage: hc_signal.py RAWDIR jobs.json JOB PLUGIN_ID"""
import json, os, re, sys, statistics
raw, jobsf, job, pid = sys.argv[1:5]
FATAL = re.compile(r"is not a type|is not installed|module \S+ (is )?not (found|installed)|Failed to load|failed to load|SyntaxError|Expected token|Unexpected token|Type \S+ unavailable|Cannot open: \S+\.qml|Cannot create delegate|Required property .* was not initialized", re.I)
ERR = re.compile(r"TypeError|ReferenceError|SyntaxError|is not a type|is not installed|module .* not found|Cannot assign|Unable to assign|Non-existent|unavailable|Cannot read propert|not a function|Binding loop|Failed to load|failed to load|Invalid property|Cannot anchor|Expected token|is not defined|Cannot open|Required property|ShellRoot|Cannot create delegate|Unexpected token", re.I)
IMG = re.compile(r"Cannot open: \S+\.(png|jpe?g|gif|webp|svg|ico|mp4|webm)", re.I)
def lines(n):
    try: return open(os.path.join(raw, n), errors="replace").read().splitlines()
    except Exception: return []
meta = next((j for j in json.load(open(jobsf))["jobs"] if j["job"] == job), {})
rec = dict(job=job, plugin_id=pid, batch=meta.get("batch"), kinds=meta.get("kinds"))
rec["meta"] = {k: v for k, v in meta.items() if k not in ("dropped",)}
rc = lines("rc.txt"); rec["rc"], rec["elapsed_s"] = ((rc[0].split() + [None, None])[:2] if rc else (None, None))
rec["mode"] = (lines("mode.txt") or [None])[0]
rec["timeout"] = rec["rc"] in ("124", "137")
il = lines("ipc_list.txt")
try:
    L = json.loads(il[0]); m = [x for x in L if x.get("id") == pid]; rec["listed"] = bool(m); rec["enabled"] = m[0].get("enabled") if m else None; rec["ipc_ok"] = True
except Exception: rec["listed"] = None; rec["enabled"] = None; rec["ipc_ok"] = False; rec["ipc_err"] = " ".join(il)[:200]
tg = lines("toggle.txt"); exits = [t for t in tg if t.startswith("exit=")]
rec["toggle_ok"] = (all(t == "exit=0" for t in exits) if exits else None); rec["toggle_out"] = [t[:160] for t in tg if not t.startswith("exit=")][:3]
S = [l.split("\t") for l in lines("samples.tsv")]
dead = [int(s[0]) for s in S if len(s) > 1 and s[1] == "DEAD"]; rec["died_at_s"] = min(dead) if dead else None
by = {}
for s in S:
    if len(s) < 2 or s[1] == "DEAD": continue
    f = s[1].split()
    try: by[int(s[0])] = (float(f[1]), int(f[2]) // 1024)
    except Exception: pass
ks = sorted(by)
rec["rss_mb"] = max((v[1] for v in by.values()), default=None)
early = [by[k][1] for k in ks if 3 <= k <= 6]; late = [by[k][1] for k in ks[-4:]]
rec["rss_growth_mb"] = (round(statistics.mean(late) - statistics.mean(early)) if early and late else None)
lt = [by[k][0] for k in ks if k >= 19]; rec["cpu_late"] = round(statistics.mean(lt), 1) if lt else None
txt = lines("qs_stdout.txt") + lines("qslog.txt")
ansi = re.compile(r"\x1b\[[0-9;]*m"); txt = [ansi.sub("", t) for t in txt]
def norm(t): return re.sub(r"\s+", " ", re.sub(r"/[^ \"']*/work/[^/ ]+/(home|shell)/", "~/", t)).strip()[:260]
rel = [norm(t) for t in txt if ("plugins/" + pid) in t or "Process failed to start" in t]
host = [norm(t) for t in txt if (("PluginRegistry" in t or "manifest" in t.lower() or "Required property" in t or "ShellRoot" in t) and (pid in t or "Required property" in t or "ShellRoot" in t))]
errs = sorted({t for t in rel + host if ERR.search(t) and not IMG.search(t)})
rec["qml_fatal"] = [e for e in errs if FATAL.search(e)][:6]
rec["qml_warnings"] = [e for e in errs if not FATAL.search(e) and "Binding loop" not in e][:10]
rec["binding_loops"] = len([e for e in errs if "Binding loop" in e])
rec["log_lines"] = sorted({norm(t) for t in txt if pid in t})[:30]
rec["missing_bins"] = sorted({m.group(1) for t in txt for m in [re.search(r'Command: QList\("([^"]+)"', t)] if m and "failed to start" in t})[:8]
rec["wayland_fail"] = any(re.search(r"Failed to connect to (the )?Wayland|could not connect to display|No Qt platform plugin|cannot connect to Wayland", t, re.I) for t in txt)
# processes spawned by the shell (descendants of quickshell), argv unique
P = {}
for l in lines("procs.tsv"):
    f = l.split("\t", 1)
    if len(f) < 2: continue
    g = f[1].split(None, 6)
    if len(g) < 6: continue
    try: s, (pid_, ppid, cpu, rss, nlwp, comm) = int(f[0]), (int(g[0]), int(g[1]), g[2], g[3], g[4], g[5])
    except Exception: continue
    P.setdefault(s, []).append((pid_, ppid, comm, g[6] if len(g) > 6 else comm))
cmds = []; seen = set()
for s, rows in sorted(P.items()):
    qs = {p for p, pp, c, a in rows if re.match(r"(/\S*/)?(quickshell|qs)\b", c) or re.match(r"(/\S*/)?quickshell\b", a)}
    desc = set(qs)
    for _ in range(8):
        desc |= {p for p, pp, c, a in rows if pp in desc}
    for p, pp, c, a in rows:
        if p in desc and p not in qs and a not in seen: seen.add(a); cmds.append(a[:300])
rec["child_cmds"] = cmds[:120]
rec["extra_quickshell"] = sum(1 for a in cmds if re.match(r"(/\S*/)?(quickshell|qs)(\s|$)", a))
shim = []
for l in lines("shim.log"):
    f = l.split("\t")
    if len(f) >= 2 and [f[1]] + [x[:200] for x in f[2:]] not in shim: shim.append([f[1]] + [x[:200] for x in f[2:]])   # unique calls only
rec["shim_calls"] = [c for c in shim if c[0] != "hyprctl"][:100] + [c for c in shim if c[0] == "hyprctl"][:20]
def ent(n):
    out = []
    for l in lines(n):
        f = l.split("\t")
        if len(f) >= 3: out.append(dict(path=f[0], mode=f[1], type=f[2], size=int(f[3]) if len(f) > 3 and f[3].isdigit() else None, link=f[4] if len(f) > 4 else ""))
    return out
rec["tmp_entries"] = ent("tmp_entries.tsv")[:100]; rec["files_written"] = [e for e in ent("files_written.tsv") if not e["path"].startswith((".cache/", ".local/state/quickshell"))][:100]
rec["ipc_out"] = {l.split("\t")[0]: l.split("\t", 1)[1][:300] for l in lines("ipc_out.txt") if "\t" in l}
rec["leaked"] = [l[:160] for l in lines("leaked_procs.txt")][:6]
kinds = set(meta.get("kinds") or [])
reasons = []; verdict = "works"
if not S or rec["wayland_fail"] or (rec["ipc_ok"] is False and (rec["died_at_s"] is None or rec["died_at_s"] <= 3)):
    verdict = "unsure"; reasons.append("harness: shell did not start or never answered IPC (rc=%s) %s" % (rec["rc"], (rec.get("ipc_err") or "")[:100]))
else:
    if rec["died_at_s"] is not None and rec["died_at_s"] < 20: verdict = "broken"; reasons.append(f"shell died at s{rec['died_at_s']}")
    if rec["listed"] is False: verdict = "broken"; reasons.append("plugin not listed/registered by the shell")
    if rec["qml_fatal"]: verdict = "broken"; reasons += ["qml-fatal: " + e[-140:] for e in rec["qml_fatal"][:2]]
    if rec["toggle_ok"] is False and (kinds & {"panel", "overlay", "menu"}) and not (kinds & {"bar", "bar-widget"}): verdict = "broken"; reasons.append("toggle IPC failed: " + " ".join(rec["toggle_out"])[:100])
    if (rec["rss_growth_mb"] or 0) > 300: verdict = "broken"; reasons.append(f"memory runaway +{rec['rss_growth_mb']} MB / 20 s")
    if verdict == "works" and rec["missing_bins"]: verdict = "unsure"; reasons.append("dependency: " + ",".join(rec["missing_bins"]))
    if rec["timeout"] and verdict == "works": verdict = "unsure"; reasons.append("job timeout")
rec["verdict"] = verdict; rec["works"] = verdict == "works"; rec["reasons"] = reasons; rec["error"] = reasons[0] if verdict == "broken" and reasons else None
# normalised signature of everything the shell printed about the plugin (pair comparison: pre vs post)
rec["signature"] = sorted({re.sub(r"\[\d+:\d+\]|:\d+(:\d+)?\b|0x[0-9a-f]+", "", e)[:200] for e in errs})[:25]
print(json.dumps(rec, ensure_ascii=False))
