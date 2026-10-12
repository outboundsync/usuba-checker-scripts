#!/usr/bin/env python3
"""Runtime functional test: install one plugin into a throwaway HOME and boot the REAL Omarchy shell
(omarchy-src shell/, Quickshell master @4f508be on Qt 6.11.3) on a headless sway (wlroots) compositor,
inside a bubblewrap sandbox (read-only /, private /tmp, no network). Enable it via shell.json exactly like
`omarchy plugin enable`, summon it through the shell's own IPC (`shell summon <id>`), then probe registry /
loader / bar-geometry state through one harness-only IPC function (ftProbe). Log lines attributable to the
plugin's directory (or the shell's per-plugin failure messages) are collected as load/runtime errors.
"""
import json, os, re, shutil, subprocess, tempfile, hashlib, time

QS = "/opt/qs611/bin/qs"
OMARCHY = "/opt/ft/omarchy"
SWAY_SOCK = "/opt/ft/swayrt/wayland-1"
RUNS = "/opt/ft/runs"
ENV_BASE = {
    "LD_LIBRARY_PATH": "/opt/wl/lib/x86_64-linux-gnu:/opt/qt/6.11.3/gcc_64/lib",
    "QML_IMPORT_PATH": "/opt/qs611/qml", "QT_QPA_PLATFORM": "wayland", "WAYLAND_DISPLAY": SWAY_SOCK,
    "OMARCHY_PATH": OMARCHY, "PATH": f"/opt/ft/stubbin:{OMARCHY}/bin:/usr/local/bin:/usr/bin:/bin",
    "LANG": "C.UTF-8", "QT_QUICK_BACKEND": "software", "XDG_SESSION_TYPE": "wayland",
}
SENTINELS = {".config/hypr/hyprland.conf": "# sentinel hyprland\nsource = ~/.config/hypr/looknfeel.conf\n",
             ".config/hypr/looknfeel.conf": "# sentinel looknfeel\n", ".config/hypr/looknfeel.lua": "-- sentinel\n",
             ".config/hypr/bindings.conf": "# sentinel bindings\nbind = SUPER, Return, exec, alacritty\n",
             ".config/hypr/monitors.conf": "# sentinel monitors\n", ".bashrc": "# sentinel bashrc\n"}
ALLOWED_WRITE = re.compile(r"^(\.cache/|\.local/state/|\.local/share/(?!omarchy)|\.config/omarchy/plugins/|\.config/omarchy/shell\.json$|\.config/(?!hypr/|omarchy/|systemd/|autostart/|environment\.d/)[^/]+/)")

DRIVER = r'''#!/bin/bash
cd "$FT_DIR"
"$QS" -p "$OMARCHY_PATH/shell" > "$FT_DIR/qs.log" 2>&1 &
QPID=$!
ipc() { timeout 4 "$QS" ipc -p "$OMARCHY_PATH/shell" call shell "$@" 2>>"$FT_DIR/ipc.err"; }
for i in $(seq 1 40); do sleep 0.25; ipc ping >/dev/null && break; kill -0 $QPID 2>/dev/null || break; done
sleep 2.5
ipc ftProbe "$FT_ID" > "$FT_DIR/probe0.json"
if [ -n "$FT_SUMMON" ]; then ipc summon "$FT_ID" '{}' > "$FT_DIR/summon.txt"; fi
sleep 2.5
ipc ftProbe "$FT_ID" > "$FT_DIR/probe1.json"
sleep 2
ipc ftProbe "$FT_ID" > "$FT_DIR/probe2.json"
kill -0 $QPID 2>/dev/null && echo alive > "$FT_DIR/alive"
kill $QPID 2>/dev/null; sleep 0.3; kill -9 $QPID 2>/dev/null; wait $QPID 2>/dev/null
echo $? > "$FT_DIR/qs.rc"
'''

ERR_PAT = re.compile(r"(Error|error|failed|is not a type|not installed|Cannot|Unable to|Invalid|Expected token|Unexpected|undefined|is not a function|Non-existent|Type .* unavailable|is not defined|No such|Unknown|not found|cannot)")
SOFT_PAT = re.compile(r"(Read of .* failed: File does not exist|summon: no live bar widget|IpcHandler at|another handler is registered for target|Host \S+ not found|Network access is disabled|Connection refused|Temporary failure in name resolution|Name or service not known|QNetworkReply|Process failed to start, likely because the binary could not be found|Binding loop detected|QFont::|Could not connect to DBus|pipewire|polkit)")

def _hash(p):
    try: return hashlib.sha1(open(p, "rb").read()).hexdigest()
    except Exception: return None

def _snapshot(home):
    out = {}
    for r, ds, fs in os.walk(home):
        for f in fs:
            p = os.path.join(r, f); rel = os.path.relpath(p, home)
            try: st = os.lstat(p); out[rel] = (st.st_size, st.st_mtime_ns)
            except Exception: pass
    return out

def install_files(dst, files):
    for p, c in files.items():
        if ".." in p or p.startswith("/"): continue
        fp = os.path.join(dst, p); os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "w") as f: f.write(c)

def shell_config(pid, kinds):
    cfg = json.load(open(f"{OMARCHY}/config/omarchy/shell.json"))
    cfg.setdefault("plugins", [])
    if "bar-widget" in kinds:
        cfg["bar"]["layout"].setdefault("right", []).insert(0, {"id": pid})
    if "bar" in kinds: cfg["bar"]["id"] = pid
    if any(k in kinds for k in ("panel", "overlay", "menu", "service")):
        cfg["plugins"].append({"id": pid})
    return cfg

def run(files=None, src_dir=None, timeout=40, keep=False):
    """files: {relpath: text} or src_dir: a plugin folder. Returns dict."""
    os.makedirs(RUNS, exist_ok=True)
    S = tempfile.mkdtemp(dir=RUNS, prefix="r")
    home = os.path.join(S, "home"); os.makedirs(home)
    res = {"errors": [], "soft": [], "checks": {}}
    try:
        if src_dir:
            man = json.load(open(os.path.join(src_dir, "manifest.json")))
        else:
            man = json.loads(files["manifest.json"])
        pid = str(man.get("id")); kinds = man.get("kinds") or []
        if not isinstance(kinds, list): kinds = []
        res["id"], res["kinds"] = pid, kinds
        pdir = os.path.join(home, ".config/omarchy/plugins", re.sub(r"[^A-Za-z0-9._-]", "_", pid) or "x")
        if src_dir: shutil.copytree(src_dir, pdir, symlinks=True, ignore=shutil.ignore_patterns(".git"))
        else: os.makedirs(pdir); install_files(pdir, files)
        for rel, txt in SENTINELS.items():
            fp = os.path.join(home, rel); os.makedirs(os.path.dirname(fp), exist_ok=True); open(fp, "w").write(txt)
        json.dump(shell_config(pid, kinds), open(os.path.join(home, ".config/omarchy/shell.json"), "w"), indent=1)
        before = _snapshot(home)
        rt = os.path.join(S, "rt"); os.makedirs(rt, mode=0o700)
        open(os.path.join(S, "driver.sh"), "w").write(DRIVER)
        summon = any(k in kinds for k in ("panel", "overlay", "menu", "bar-widget"))
        env = dict(ENV_BASE, HOME=home, XDG_RUNTIME_DIR=rt, FT_DIR=S, FT_ID=pid, QS=QS, FT_SUMMON="1" if summon else "",
                   XDG_CONFIG_HOME=os.path.join(home, ".config"), XDG_CACHE_HOME=os.path.join(home, ".cache"),
                   XDG_DATA_HOME=os.path.join(home, ".local/share"), XDG_STATE_HOME=os.path.join(home, ".local/state"))
        cmd = ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
               "--bind", S, S, "--bind", "/opt/ft/swayrt", "/opt/ft/swayrt", "--unshare-net", "--unshare-pid",
               "--unshare-ipc", "--die-with-parent", "--clearenv"]
        for k, v in env.items(): cmd += ["--setenv", k, v]
        cmd += ["bash", os.path.join(S, "driver.sh")]
        t0 = time.time()
        try: subprocess.run(cmd, timeout=timeout, capture_output=True)
        except subprocess.TimeoutExpired: res["errors"].append("harness timeout (shell hung)")
        res["elapsed"] = round(time.time() - t0, 1)
        log = open(os.path.join(S, "qs.log"), errors="replace").read() if os.path.exists(os.path.join(S, "qs.log")) else ""
        def probe(n):
            try: return json.loads(open(os.path.join(S, n)).read().strip().splitlines()[-1])
            except Exception: return None
        p0, p1, p2 = probe("probe0.json"), probe("probe1.json"), probe("probe2.json")
        best = dict(p2 or p1 or p0 or {})
        for p in (p0, p1, p2):  # loaders are async: take the most-loaded observation
            if not p: continue
            for k in ("installed", "widgetRegistered", "service", "barLoaded", "open"):
                best[k] = bool(best.get(k)) or bool(p.get(k))
            if p.get("panel") and p["panel"].get("hasItem"): best["panel"] = p["panel"]
            if p.get("bar") and not best.get("bar"): best["bar"] = p["bar"]
        res["probe"] = best or None
        res["alive"] = os.path.exists(os.path.join(S, "alive"))
        res["summon"] = open(os.path.join(S, "summon.txt")).read().strip() if os.path.exists(os.path.join(S, "summon.txt")) else None
        # attribute log lines
        marker = "/plugins/" + os.path.basename(pdir) + "/"
        log = re.sub(r"\x1b\[[0-9;]*m", "", log)
        lines = log.splitlines()
        for i, ln in enumerate(lines):
            attributed = marker in ln or re.search(r"(plugin|widget|bar option|summon)\b[^\n]*\b" + re.escape(pid) + r"\b", ln, re.I)
            if not attributed and i > 0 and marker in lines[i - 1] and not re.match(r"^\s*(INFO|WARN|ERROR|DEBUG)", ln): attributed = True
            if not attributed: continue
            s = re.sub(r"file://\S*?/plugins/[^/]+/", "", ln.strip())[:300]
            if SOFT_PAT.search(ln): res["soft"].append(s)
            elif re.search(r"\b(WARN|ERROR|FATAL|CRIT)", ln) or ERR_PAT.search(ln): res["errors"].append(s)
        if re.search(r"(FATAL|Segmentation|core dumped|qFatal)", log) and not res["alive"]:
            res["errors"].append("shell crashed")
        if not p0 and not p1 and not p2: res["errors"].append("shell did not come up / IPC unreachable")
        res["log_tail"] = [l for l in lines if marker in l][:20]
        # functional assertions per kind
        pr = res["probe"] or {}
        C = res["checks"]
        C["registered"] = bool(pr.get("installed"))
        if not C["registered"]: res["errors"].append("PluginRegistry rejected/didn't discover the plugin")
        if "bar-widget" in kinds:
            g = [x for x in (pr.get("bar") or []) if isinstance(x, dict)]
            C["widget_component"] = bool(pr.get("widgetRegistered"))
            C["widget_size"] = [g[0].get("itemWidth"), g[0].get("itemHeight")] if g else None
            C["widget_slot"] = [g[0].get("width"), g[0].get("height")] if g else None
            if not C["widget_component"]: res["errors"].append("bar-widget component never registered (load failed)")
            elif not g: res["errors"].append("bar-widget not instantiated in bar")
            elif not (g[0].get("width", 0) > 0 and g[0].get("height", 0) > 0): res["errors"].append(f"bar-widget has zero size {C['widget_slot']}")
            C["panel_opened"] = bool(pr.get("open"))
        for k in ("panel", "overlay", "menu"):
            if k in kinds:
                pl = pr.get("panel")
                C["panel"] = pl
                if not pl or not pl.get("hasItem"):
                    res["errors"].append(f"{k} never instantiated after summon (status={pl and pl.get('status')})")
                break
        if "service" in kinds:
            C["service"] = bool(pr.get("service"))
            if not C["service"]: res["errors"].append("service instance not created")
        if "bar" in kinds:
            C["bar_active"] = pr.get("activeBarId") == pid and pr.get("barLoaded")
            if not C["bar_active"]: res["errors"].append(f"bar option not active (activeBarId={pr.get('activeBarId')})")
        # filesystem side effects
        after = _snapshot(home)
        for rel, txt in SENTINELS.items():
            fp = os.path.join(home, rel)
            if not os.path.exists(fp) or open(fp, errors="replace").read() != txt:
                res["errors"].append(f"DANGEROUS: modified/deleted protected file ~/{rel}")
        bad = [r for r in after if (r not in before or after[r] != before[r]) and not ALLOWED_WRITE.match(r) and r not in SENTINELS]
        for r in bad[:10]: res["errors"].append(f"wrote outside plugin data dirs: ~/{r}")
        res["writes"] = sorted(r for r in after if (r not in before or after[r] != before[r]) and not r.startswith(".cache/fontconfig"))[:30]
    except Exception as e:
        res["errors"].append(f"harness: {type(e).__name__}: {e}")
    finally:
        if not keep: shutil.rmtree(S, ignore_errors=True)
        else: res["dir"] = S
    res["pass"] = not res["errors"]
    return res

if __name__ == "__main__":
    import sys
    print(json.dumps(run(src_dir=sys.argv[1], keep="--keep" in sys.argv), indent=1))
