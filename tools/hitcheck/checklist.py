#!/usr/bin/env python3
"""Hardware checklist + per-plugin review sheet for the S2 clean set (box side; reads hitcheck-results.jsonl and the raw/<job>/ directories returned from the Dell).

Per plugin (auto, from the sandboxed run + host-side observer):
  loads       listed and enabled, shell alive at the end, no fatal QML message, no missing dependency, no timeout
  surface     panel/overlay/menu kinds: a new compositor surface owned by the plugin's shell appeared after toggle (OBSERVE=1)
  closes      ... and it was gone after the second toggle
  errors      QML warnings / binding loops / non-fatal errors printed about the plugin
  strange     refused PATH-shim calls (network, install, sudo...), leaked processes, files written outside the cache dirs, entries left in /tmp, CPU > 60 % late, RSS growth > 100 MB,
              extra quickshell instances, child commands that look destructive (rm -rf, dd, mkfs, chmod 777, curl|sh, ssh ...)
Auto verdict: FAIL (does not load / dependency / timeout), REVIEW (any surface miss or strange flag or error warnings), PASS_AUTO (everything clean). PASS_AUTO is still only a hardware smoke result:
"clean" needs the human spot-check (all REVIEW rows + a seeded sample of PASS_AUTO rows) and the code review; this tool never labels a plugin clean by itself.
Outputs: s2_hw_results.jsonl, review_sheet.csv, review_sheet.html (thumbnails, ordered for review), s2_hw_summary.json.

usage: python3 checklist.py RESULTS.jsonl --raw RAWDIR --candidates s2_candidates.jsonl --out OUTDIR [--spot-frac 0.10 --spot-min 30 --seed 1]
"""
import argparse
import csv
import html
import json
import os
import random
import re
import shutil

DESTRUCT = re.compile(r"\brm\s+-[a-z]*r[a-z]*f?\s+(/|~|\$HOME)|\bdd\s+if=|\bmkfs|chmod\s+-?R?\s*777|\|\s*(ba)?sh\b|\bssh\b|\bscp\b|\bnc\s|\bsudo\b|\bpkexec\b|/dev/sd|\bshred\b", re.I)
BENIGN_FILES = (".cache/", ".config/omarchy/", ".local/state/", ".local/share/", ".cache")


def evaluate(r, cand):
    kinds = set(r.get("kinds") or [])
    obs = r.get("obs")
    f = {}
    f["loads"] = bool(r.get("listed") and r.get("enabled") is not False and r.get("died_at_s") is None and not r.get("qml_fatal") and not r.get("missing_bins") and not r.get("timeout")
                      and r.get("verdict") == "works")
    surf_kind = bool(kinds & {"panel", "overlay", "menu"})
    if obs is None:
        f["surface"] = None
        f["closes"] = None
    else:
        opened = obs.get("opened") or []
        f["surface"] = bool(opened) if surf_kind else None
        f["closes"] = (bool(obs.get("closed")) and not obs.get("still_open")) if (surf_kind and opened) else None
    warns = list(r.get("qml_warnings") or [])
    f["errors"] = len(warns) + (r.get("binding_loops") or 0)
    strange = []
    shim = [c for c in (r.get("shim_calls") or []) if c and c[0] not in ("hyprctl", "pacman", "flatpak", "systemctl", "gsettings", "dconf", "loginctl", "busctl")]
    if shim:
        strange.append("refused-calls:" + ",".join(sorted({c[0] for c in shim})))
    # the runner's own inotifywait evidence watcher is always alive at the end; it is not the plugin's
    leaked = [x for x in (r.get("leaked") or []) if "inotifywait" not in str(x)]
    if leaked:
        strange.append("leaked-procs")
    fw = [e["path"] for e in (r.get("files_written") or []) if not e["path"].startswith(BENIGN_FILES) and e["type"] != "d"]
    if fw:
        strange.append("files-written:" + ";".join(fw[:3]))
    if r.get("tmp_entries"):
        strange.append("tmp-entries:%d" % len(r["tmp_entries"]))
    if (r.get("cpu_late") or 0) > 60:
        strange.append("cpu-late:%s" % r["cpu_late"])
    if (r.get("rss_growth_mb") or 0) > 100:
        strange.append("rss-growth:%s" % r["rss_growth_mb"])
    if r.get("extra_quickshell"):
        strange.append("extra-quickshell")
    bad = [c for c in (r.get("child_cmds") or []) if DESTRUCT.search(c)]
    if bad:
        strange.append("suspicious-cmd:" + bad[0][:80])
    f["strange"] = strange
    if not f["loads"]:
        verdict = "FAIL"
    elif f["surface"] is False or f["closes"] is False or f["errors"] or strange or (obs is None and surf_kind):
        verdict = "REVIEW"
    else:
        verdict = "PASS_AUTO"
    return f, verdict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results")
    ap.add_argument("--raw", required=True)
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--spot-frac", type=float, default=0.10)
    ap.add_argument("--spot-min", type=int, default=30)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    cands = {json.loads(line)["job"]: json.loads(line) for line in open(a.candidates)}
    latest = {}
    for line in open(a.results):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        latest[r["job"]] = r
    rows = []
    for job, r in sorted(latest.items()):
        c = cands.get(job, {})
        f, v = evaluate(r, c)
        shots = []
        od = os.path.join(a.raw, job, "obs")
        if os.path.isdir(od):
            for fn in sorted(os.listdir(od)):
                if fn.endswith(".png"):
                    dst = os.path.join(a.out, "shots", job)
                    os.makedirs(dst, exist_ok=True)
                    shutil.copy2(os.path.join(od, fn), os.path.join(dst, fn))
                    shots.append(f"shots/{job}/{fn}")
        rows.append(dict(job=job, plugin_id=r["plugin_id"], repo=c.get("repo"), commit=c.get("commit"), kinds=r.get("kinds"), hw_verdict=r.get("verdict"), auto=v, checks=f,
                         reasons=r.get("reasons"), qml_warnings=(r.get("qml_warnings") or [])[:4], opened=(r.get("obs") or {}).get("opened"), shots=shots, human=None, eval_only=True, provisional=True))
    rng = random.Random(a.seed)
    passes = [x for x in rows if x["auto"] == "PASS_AUTO"]
    k = min(len(passes), max(a.spot_min, int(len(passes) * a.spot_frac)))
    spot = {x["job"] for x in rng.sample(passes, k)}
    for x in rows:
        x["spot_check"] = x["auto"] == "REVIEW" or x["job"] in spot
    with open(os.path.join(a.out, "s2_hw_results.jsonl"), "w") as fo:
        fo.writelines(json.dumps(x) + "\n" for x in rows)
    with open(os.path.join(a.out, "review_sheet.csv"), "w", newline="") as fo:
        w = csv.writer(fo)
        w.writerow(["job", "plugin_id", "repo", "kinds", "auto", "loads", "surface", "closes", "errors", "strange", "spot_check", "human_verdict(clean|not_clean|unsure)", "human_notes"])
        for x in sorted(rows, key=lambda x: (not x["spot_check"], x["auto"], x["job"])):
            c = x["checks"]
            w.writerow([x["job"], x["plugin_id"], x["repo"], ",".join(x["kinds"] or []), x["auto"], c["loads"], c["surface"], c["closes"], c["errors"], "|".join(c["strange"]), x["spot_check"], "", ""])
    with open(os.path.join(a.out, "review_sheet.html"), "w") as fo:
        fo.write("<meta charset=utf-8><title>S2 hardware review sheet (PROVISIONAL)</title><style>body{font:13px sans-serif}td{vertical-align:top;border-top:1px solid #ccc;padding:4px}img{max-width:360px;max-height:200px;border:1px solid #999}</style>"
                 "<h2>S2 hardware review sheet - PROVISIONAL, eval-only</h2><table>")
        for x in sorted(rows, key=lambda x: (not x["spot_check"], x["auto"], x["job"])):
            if not x["spot_check"]:
                continue
            c = x["checks"]
            fo.write("<tr><td><b>%s</b><br>%s<br>%s<br>auto=%s spot=%s</td><td>loads=%s surface=%s closes=%s errors=%s<br>%s<br>%s</td><td>%s</td></tr>" % (
                html.escape(x["plugin_id"]), html.escape(x["repo"] or ""), ",".join(x["kinds"] or []), x["auto"], x["spot_check"], c["loads"], c["surface"], c["closes"], c["errors"],
                html.escape("; ".join(c["strange"])), html.escape(" | ".join(x["qml_warnings"])[:300]), "".join('<img src="%s">' % s for s in x["shots"])))
        fo.write("</table>")
    cnt = lambda p: sum(1 for x in rows if p(x))
    summ = dict(provisional=True, n=len(rows), auto={v: cnt(lambda x, v=v: x["auto"] == v) for v in ("PASS_AUTO", "REVIEW", "FAIL")}, hw_verdict={v: cnt(lambda x, v=v: x["hw_verdict"] == v) for v in ("works", "broken", "unsure")},
                spot_check=cnt(lambda x: x["spot_check"]), with_screenshots=cnt(lambda x: bool(x["shots"])),
                surface_kinds_opened=cnt(lambda x: x["checks"]["surface"] is True), surface_kinds_not_opened=cnt(lambda x: x["checks"]["surface"] is False))
    json.dump(summ, open(os.path.join(a.out, "s2_hw_summary.json"), "w"), indent=1)
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
