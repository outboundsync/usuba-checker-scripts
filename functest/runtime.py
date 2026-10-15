#!/usr/bin/env python3
"""Runtime functional test: install one plugin into a throwaway HOME and boot the REAL Omarchy shell
(Omarchy 4.0.0.alpha = basecamp/omarchy @ c668141, whose shell/ is byte-identical to /usr/share/omarchy/shell on a reference Omarchy laptop;
built by dell_env/setup.py) with Quickshell master @4f508be on Qt 6.11.3 on a headless sway (wlroots) compositor,
inside a bubblewrap sandbox (read-only /, private /tmp, no network). Enable it via shell.json exactly like
`omarchy plugin enable`, summon it through the shell's own IPC (`shell summon <id>`), then probe registry /
loader / bar-geometry state through one harness-only IPC function (ftProbe). Log lines attributable to the
plugin's directory (or the shell's per-plugin failure messages) are collected as load/runtime errors.
"""
import json, os, re, shutil, stat, subprocess, tempfile, hashlib, time, sys, threading
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "dell_env"))
import setup as dell_setup
sys.path.insert(0, os.path.dirname(HERE))
from usuba import policy as _policy
from binaries import resolves, KNOWN

QS = "/opt/qs611/bin/qs"
OMARCHY = os.environ.get("FT_OMARCHY", "/opt/ft/omarchy-4.0.4")   # the BUILT runtime tree (dell_env/setup.py builds it, incl. the ftProbe patch); the static Checker's API reference is separate, see refpaths.py
THEME = os.environ.get("FT_THEME", "catppuccin-latte")   # light theme like the Dell's: dark-hardcoded widgets lose contrast
SHIMS = "/opt/ft/shims-dell"
HYPRCTL = os.path.join(HERE, "dell_env/hyprctl.py")
HYPR_FX = os.path.join(HERE, "fixtures/hyprland-0.56.2")
SWAY_SOCK = "/opt/ft/swayrt/wayland-1"
RUNS = "/opt/ft/runs"
ENV_BASE = {
    "LD_LIBRARY_PATH": "/opt/wl/lib/x86_64-linux-gnu:/opt/qt/6.11.3/gcc_64/lib",
    "QML_IMPORT_PATH": "/opt/qs611/qml", "QT_QPA_PLATFORM": "wayland", "FT_SWAYCONF": "/opt/ft/sway.conf",
    "OMARCHY_PATH": OMARCHY, "PATH": SHIMS, "FT_REALPATH": f"{OMARCHY}/bin:/usr/local/bin:/usr/bin:/bin",
    "FT_HYPRCTL": HYPRCTL, "FT_HYPR_MONNAME": "HEADLESS-1", "FT_HYPR_FX": HYPR_FX,
    "LANG": "C.UTF-8", "QT_QUICK_BACKEND": "software", "XDG_SESSION_TYPE": "wayland",
}
SENTINELS = {".config/hypr/hyprland.conf": "# sentinel hyprland\nsource = ~/.config/hypr/looknfeel.conf\n",
             ".config/hypr/looknfeel.conf": "# sentinel looknfeel\n", ".config/hypr/looknfeel.lua": "-- sentinel\n",
             ".config/hypr/bindings.conf": "# sentinel bindings\nbind = SUPER, Return, exec, alacritty\n",
             ".config/hypr/monitors.conf": "# sentinel monitors\n", ".bashrc": "# sentinel bashrc\n"}
ALLOWED_WRITE = re.compile(r"^(\.cache/|\.local/state/|\.local/share/(?!omarchy)|\.config/omarchy/plugins/|\.config/omarchy/shell\.json$|\.config/(?!hypr/|omarchy/|systemd/|autostart/|environment\.d/)[^/]+/)")

DRIVER = r'''#!/bin/bash
# Everything the harness scores (shell log, probes, screenshots) leaves the sandbox on this script's stdout pipe, never via
# files under $FT_DIR, so a plugin (same uid, can write $HOME = $FT_DIR/home) cannot rewrite its own evidence.
cd "$FT_DIR"
SHIMPATH=$PATH; export PATH=/usr/bin:/bin
emit() { local tag=$1; shift; "$@" 2>/dev/null | tr -d '\n' | sed 's/^/'"$tag"' /'; echo; }
shot() { grim - 2>/dev/null | base64 -w 3000 | sed 's/^/'"$1"' /'; }
# fake Hyprland IPC sockets (Quickshell.Hyprland) answering with the recorded 0.56.2 reply shapes
export HYPRLAND_INSTANCE_SIGNATURE=ft_dell_0562
FT_HYPRLOG="$FT_DIR/hypr_requests.log" /usr/bin/python3 "$FT_HYPRCTL" --serve "$XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE" &
HYPID=$!
# private headless compositor per run (screenshots must not mix with concurrent runs)
WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1 WAYLAND_DISPLAY= sway -c "$FT_SWAYCONF" > /dev/null 2>&1 &
SWPID=$!
for i in $(seq 1 40); do [ -S "$XDG_RUNTIME_DIR/wayland-1" ] && break; sleep 0.1; done
export WAYLAND_DISPLAY=wayland-1
ID=$FT_ID; SUMMON=$FT_SUMMON; LIVE=$FT_LIVE_ENABLE
env -u FT_DIR -u FT_ID -u FT_SUMMON -u FT_LIVE_ENABLE -u FT_SWAYCONF -u FT_HYPRLOG PATH="$SHIMPATH" "$QS" -p "$OMARCHY_PATH/shell" > >(sed -u 's/^/L /') 2>&1 &
QPID=$!
ipc() { timeout 4 "$QS" ipc -p "$OMARCHY_PATH/shell" call shell "$@" 2>/dev/null; }
for i in $(seq 1 40); do sleep 0.25; ipc ping >/dev/null && break; kill -0 $QPID 2>/dev/null || break; done
sleep 2.5
if [ -n "$LIVE" ]; then emit ENABLE ipc enablePlugin "$ID" '{}'; sleep 3; fi
emit P0 ipc ftProbe "$ID"
emit M0 ps -o rss= -p $QPID
shot S0
if [ -n "$SUMMON" ]; then emit SUMMON ipc summon "$ID" '{}'; fi
sleep 2.5
emit P1 ipc ftProbe "$ID"
sleep 2
emit P2 ipc ftProbe "$ID"
shot S1
# usage cycle (USB-D04, learned on the Dell): close + reopen through the shell's IPC, then re-probe; runaway RSS (USB-D05)
echo "U usage-begin"
if [ -n "$SUMMON" ]; then emit SUMMON2 ipc summon "$ID" '{}'; sleep 1; emit SUMMON3 ipc summon "$ID" '{}'; fi
sleep 2
emit P3 ipc ftProbe "$ID"
emit M3 ps -o rss= -p $QPID
kill -0 $QPID 2>/dev/null && echo "ALIVE 1"
kill $QPID 2>/dev/null; sleep 0.3; kill -9 $QPID 2>/dev/null; wait $QPID 2>/dev/null
kill $SWPID $HYPID 2>/dev/null
sleep 0.2
'''

MEM_FAIL_MB, MEM_WARN_MB = 300, 150   # USB-D05 thresholds (Dell: median shell RSS 284 MB; growth >150 MB in 20 s seen in 11/4596 jobs)
ERR_PAT = re.compile(r"(Error|error|failed|is not a type|not installed|Cannot|Unable to|Invalid|Expected token|Unexpected|undefined|is not a function|Non-existent|Type .* unavailable|is not defined|No such|Unknown|not found|cannot)")
SOFT_PAT = re.compile(r"(Read of .* failed: File does not exist|summon: no live bar widget|IpcHandler at|another handler is registered for target|Host \S+ not found|Network access is disabled|Connection refused|Temporary failure in name resolution|Name or service not known|QNetworkReply|Binding loop detected|QFont::|Detected anchors on an item that is managed by a layout|Cannot open: file://\S*/current/background$|Could not connect to DBus|pipewire|polkit)")
PROC_FAIL = re.compile(r"Process failed to start, likely because the binary could not be found\. Command: QList\((.*)\)")
BAD_ARG = re.compile(r"(^(undefined|null|NaN|\[object Object\])$|\bundefined\b|\[object Object\]|(^|[=:])NaN$|=null$)")
BAD_TEXT = re.compile(r"(\bundefined\b|\[object Object\]|^NaN$|\bNaN\b(?!\w)|^null$)")
NEW_SHELL_ERR = re.compile(r"(TypeError|ReferenceError|is not a function|is not defined|Cannot read property|Unable to assign|is not a type|failed to load|Cannot assign)")
# Only these break a plugin on the Dell (dell_ground_truth.jsonl): JS TypeError/ReferenceError, load/syntax/missing-file errors.
HARD_ERR = re.compile(r"(TypeError|ReferenceError|SyntaxError|RangeError|is not a type|is not defined|is not a function|failed to load|Cannot load|"
                      r"module \S+ is not installed|Expected token|Unexpected token|Syntax error|No such file|File not found|not found\b(?!.*QList)|Non-existent attached|Type \S+ unavailable|Invalid property assignment|Cannot assign to non-existent)")
# Seen on the Dell in plugins that WORK: warnings, never fails
DOWNGRADE = re.compile(r"(Cannot assign to read-only property|Unable to assign \[undefined\]|Cannot assign \[undefined\]|deprecated|QSettings|"
                       r"Binding loop|Detected anchors)", re.I)
DELL_SURFACE = re.compile(r"(hyprctl|getoption|\b(general|decoration|input|misc|animations):\w|gaps_|omarchy-[a-z]|shell\.json|PluginRegistry|Theme\b|theme colou?r)", re.I)
QML_CONSOLE_ERR = re.compile(r"\b(WARN|ERROR|CRIT)\b\s+qml:.*\b(unable to|could not|couldn't|failed|error|cannot|invalid|undefined)\b", re.I)

COLOR_REF = re.compile(r"/plugins/[^/]+/(\S+?\.qml)\[(\d+):-?\d+\]: ReferenceError: (\w+) is not defined")
def _color_ref(ln, pdir):
    """ReferenceError inside a pure colour binding (e.g. limon.todo's `property color dim: ShellColor.muted`): the colour falls back
    to its default and the plugin still works on the Dell (dell_ground_truth: limon.todo WORKS). Anything else stays hard."""
    m = COLOR_REF.search(ln)
    if not m: return False
    try: src = safe_read(os.path.join(pdir, m.group(1)), root=pdir).splitlines()[int(m.group(2)) - 1]
    except Exception: return False
    return bool(re.match(r"\s*(readonly\s+)?(property\s+color\s+\w+|[\w.]*[cC]olor)\s*:", src)) and m.group(3) in src

def safe_read(path, cap=2_000_000, root=None, binary=False):
    """Read a file the PLUGIN may have written (audit C1): refuse symlinks (O_NOFOLLOW), FIFOs/devices (regular files only,
    O_NONBLOCK so a planted FIFO cannot hang the harness), anything whose real path leaves ``root``, and cap the size."""
    if root is not None:
        rp, rr = os.path.realpath(path), os.path.realpath(root)
        if rp != rr and not rp.startswith(rr.rstrip("/") + "/"): raise OSError("path escapes " + root)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode): raise OSError("not a regular file: " + path)
        data = b""
        while len(data) < cap:
            chunk = os.read(fd, min(65536, cap - len(data)))
            if not chunk: break
            data += chunk
    finally: os.close(fd)
    return data if binary else data.decode("utf-8", "replace")

# Minimal /etc for the sandbox (audit C1): no real home, no /run sockets, no credentials. Extend with FT_SANDBOX_ETC_EXTRA=a,b
SANDBOX_ETC = ("ld.so.cache", "ld.so.conf", "ld.so.conf.d", "fonts", "localtime", "os-release", "passwd", "group", "nsswitch.conf",
               "alternatives", "sway", "xdg", "vulkan", "drirc", "locale.alias", "mime.types")
SANDBOX_OPT = ("/opt/qs611", "/opt/qt", "/opt/wl", "/opt/ft")
def sandbox_cmd(S, env, inner, runs=None, omarchy=None, here=None):
    """bwrap argv for one plugin run. Never binds /; the real /home, /root, /run (D-Bus, docker.sock), /var are replaced by tmpfs;
    a new session (no TIOCSTI into the driver's tty); env scrubbed. Pure function so tests can inspect it."""
    runs, omarchy, here = runs or RUNS, omarchy or OMARCHY, here or HERE
    c = ["bwrap", "--unshare-net", "--unshare-pid", "--unshare-ipc", "--unshare-uts", "--unshare-cgroup-try",
         "--die-with-parent", "--new-session", "--clearenv", "--ro-bind", "/usr", "/usr"]
    for d in ("bin", "sbin", "lib", "lib64"):
        if os.path.islink("/" + d): c += ["--symlink", os.readlink("/" + d), "/" + d]
        elif os.path.isdir("/" + d): c += ["--ro-bind", "/" + d, "/" + d]
    c += ["--dir", "/etc"]
    for e in SANDBOX_ETC + tuple(x for x in os.environ.get("FT_SANDBOX_ETC_EXTRA", "").split(",") if x):
        if os.path.exists("/etc/" + e): c += ["--ro-bind", "/etc/" + e, "/etc/" + e]
    c += ["--proc", "/proc", "--dev", "/dev", "--ro-bind-try", "/sys", "/sys",
          "--tmpfs", "/tmp", "--tmpfs", "/home", "--tmpfs", "/root", "--tmpfs", "/run", "--tmpfs", "/var"]
    for o in SANDBOX_OPT:
        if os.path.isdir(o): c += ["--ro-bind", o, o]
    if os.path.realpath(runs).startswith(("/opt/ft/", "/opt/ft")): c += ["--tmpfs", runs]   # other runs stay invisible
    for ro in dict.fromkeys([omarchy, here]):
        c += ["--ro-bind-try", ro, ro]
    c += ["--bind", S, S]
    for k, v in env.items(): c += ["--setenv", k, v]
    return c + list(inner)

def run_capped(cmd, timeout, cap=64 * 1024 * 1024):
    """subprocess with stdin=/dev/null and a hard cap on captured stdout (audit D8). Returns (stdout bytes, timed_out)."""
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
    buf, over = [], threading.Event()
    def pump():
        n = 0
        for chunk in iter(lambda: proc.stdout.read(65536), b""):
            n += len(chunk)
            if n > cap: over.set(); os.killpg(proc.pid, 9); break
            buf.append(chunk)
    t = threading.Thread(target=pump, daemon=True); t.start()
    timed_out = False
    try: proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        try: os.killpg(proc.pid, 9)
        except ProcessLookupError: pass
        proc.wait()
    t.join(5)
    return b"".join(buf), timed_out or over.is_set()

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

def install_theme(home):
    fc = os.path.join(home, ".config/fontconfig"); os.makedirs(fc, exist_ok=True)   # the Dell's fontconfig (monospace = JetBrainsMono Nerd Font)
    shutil.copy(f"{OMARCHY}/default/fontconfig/conf.avail/50-omarchy.conf", os.path.join(fc, "fonts.conf"))
    d = os.path.join(home, ".local/state/omarchy/current")
    os.makedirs(d, exist_ok=True)
    shutil.copytree(f"/opt/ft/themes/{THEME}", os.path.join(d, "theme"))
    open(os.path.join(d, "theme.name"), "w").write(THEME + "\n")

def shell_config(pid, kinds, live=False):
    cfg = json.load(open(f"{OMARCHY}/config/omarchy/shell.json"))
    cfg.setdefault("plugins", [])
    if pid is None: return cfg
    if "bar-widget" in kinds:   # where the Dell run put them: center section, right after the clock
        center = cfg["bar"]["layout"].setdefault("center", [])
        ci = next((i for i, e in enumerate(center) if isinstance(e, dict) and e.get("id") == "omarchy.clock"), len(center) - 1)
        center.insert(ci + 1, {"id": pid})
    if "bar" in kinds and not live: cfg["bar"]["id"] = pid
    if any(k in kinds for k in ("panel", "overlay", "menu", "service")):
        cfg["plugins"].append({"id": pid})
    return cfg

def _lum(c):
    def ch(v):
        v /= 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(c[0]) + 0.7152 * ch(c[1]) + 0.0722 * ch(c[2])
def _contrast(a, b):
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)
def ink_stats(img, box):
    """-> (n_ink_pixels, max_contrast) of a screenshot region vs its dominant (background) colour."""
    from collections import Counter
    x0, y0, x1, y1 = [int(v) for v in box]
    x0, y0 = max(0, x0), max(0, y0); x1, y1 = min(img.width, x1), min(img.height, y1)
    if x1 <= x0 or y1 <= y0: return 0, 1.0
    px = list(img.crop((x0, y0, x1, y1)).convert("RGB").get_flattened_data())
    bg = Counter(px).most_common(1)[0][0]
    cache, n, mx = {}, 0, 1.0
    for c in px:
        r = cache.get(c)
        if r is None: r = cache[c] = _contrast(c, bg)
        if r >= 1.25: n += 1
        if r > mx: mx = r
    return n, round(mx, 2)
MIN_WIDGET_CONTRAST = 1.15   # stock ~7:1, dimmed icons 1.9-2.5:1; acme.power at 1.28:1 is dim but WORKS on the Dell (ground truth), so only near-invisible fails

def norm_line(ln):
    ln = re.sub(r"\x1b\[[0-9;]*m", "", ln)
    ln = re.sub(r"/opt/ft/runs/\w+", "<RUN>", ln)
    ln = re.sub(r"^\s*[\d:.\-T ]{6,}\s*", "", ln)
    ln = re.sub(r"0x[0-9a-f]+", "0x", ln)
    ln = re.sub(r"\[\d+:-?\d+\]", "[L]", ln)
    return re.sub(r"\b\d{3,}\b", "N", ln).strip()

_BASE_LOCK = threading.Lock()
def baseline():
    """Union of log lines / top-level exec signatures of the stock shell with NO plugin (3 boots), cached per env stamp."""
    dell_setup.build()
    p = os.path.join(RUNS, f"baseline-{open(dell_setup.STAMP).read()[:12]}-{THEME}-{hashlib.sha1(open(__file__,'rb').read()).hexdigest()[:8]}.json")
    with _BASE_LOCK:
        if os.path.exists(p): return json.load(open(p))
        lines, execs = set(), set()
        for _ in range(3):
            r = run(files=None, src_dir=None, _baseline=True)
            lines |= set(r.get("_lines", [])); execs |= set(r.get("_execs", []))
        bar_lines = set()
        for _ in range(2):   # live swap to the stock bar packaged as a plugin (see dell_env/setup.py)
            r = run(src_dir="/opt/ft/refbar", _baseline="bar")
            bar_lines |= set(r.get("_lines", [])); execs |= set(r.get("_execs", []))
        b = {"lines": sorted(lines), "execs": sorted(execs), "bar_lines": sorted(bar_lines - lines)}
        os.makedirs(RUNS, exist_ok=True); json.dump(b, open(p, "w"))
        return b

def parse_exec_log(path):
    """-> list of dicts {pid, parent, argv, rc} from the shim log."""
    recs, by = [], {}
    try: data = safe_read(path, cap=8_000_000).splitlines()   # written inside the sandbox dir: no symlinks/FIFOs (audit C1)
    except Exception: return recs
    for ln in data:
        f = ln.split("\t")
        if f[0] == "S" and len(f) >= 4:
            r = {"pid": f[1], "parent": f[2], "argv": [a.replace("\\n", "\n") for a in f[3:]], "rc": None}
            recs.append(r); by[f[1]] = r
        elif f[0] == "E" and len(f) >= 3 and f[1] in by: by[f[1]]["rc"] = f[2]
    return recs
TOP_PARENTS = {"qs", "quickshell", "bwrap", ".quickshell-wra", "QThread", "QQmlThread"}
def exec_sig(argv): return norm_line(" ".join(argv))[:200]

_GPU_FX = re.compile(r"\b(layer\.effect\s*:|MultiEffect\s*\{|ShaderEffect\s*\{)")   # plain layer.enabled renders fine in software
def _uses_gpu_effects(root):
    for dp, _, fs in os.walk(root or "/nonexistent"):
        for f in fs:
            if f.endswith(".qml"):
                try:
                    if _GPU_FX.search(safe_read(os.path.join(dp, f), root=root)): return True
                except Exception: pass
    return False

def _plugin_text(root):
    out = []
    for dp, _, fs in os.walk(root):
        for f in fs:
            if f.endswith((".qml", ".js", ".sh", ".py", ".lua")) or "." not in f:
                try: out.append(safe_read(os.path.join(dp, f), cap=400000, root=root))
                except Exception: pass
    return "\n".join(out)

def run(files=None, src_dir=None, timeout=40, keep=False, _baseline=False):
    """files: {relpath: text} or src_dir: a plugin folder. Returns dict."""
    os.makedirs(RUNS, exist_ok=True)
    res = {"errors": [], "soft": [], "checks": {}}
    S = None
    try:
        S = tempfile.mkdtemp(dir=RUNS, prefix="r")   # inside the try: the run dir is removed even if build/baseline fail (audit D8)
        home = os.path.join(S, "home"); os.makedirs(home)
        if not _baseline: dell_setup.build(); base = baseline()
        else: base = None
        if _baseline is True:
            man = {"id": "ft.none", "kinds": []}
        elif src_dir:
            man = json.load(open(os.path.join(src_dir, "manifest.json")))
        else:
            man = json.loads(files["manifest.json"])
        pid = str(man.get("id")); kinds = man.get("kinds") or []
        if not isinstance(kinds, list): kinds = []
        res["id"], res["kinds"] = pid, kinds
        pdir = os.path.join(home, ".config/omarchy/plugins", re.sub(r"[^A-Za-z0-9._-]", "_", pid) or "x")
        if _baseline is True: os.makedirs(pdir)
        elif src_dir: shutil.copytree(src_dir, pdir, symlinks=True, ignore=shutil.ignore_patterns(".git"))
        else: os.makedirs(pdir); install_files(pdir, files)
        gpu_fx = _uses_gpu_effects(pdir)   # scanned before the plugin runs
        _src = _plugin_text(pdir)
        hypr_driven = bool(re.search(r"import\s+Quickshell\.Hyprland|Hyprland\.(workspaces|toplevels|monitors|focused)", _src))
        # a plugin whose stated purpose is gaps (manifest name/description) and that ships a gaps setter must actually set them
        gap_service = bool(re.search(r"\bgaps?\b|flush", json.dumps({k: man.get(k) for k in ("id", "name", "description")}), re.I)) \
            and bool(re.search(r"keyword\s+general:gaps_(out|in)|general:gaps_(out|in)[^\n]{0,80}keyword", _src)) and "service" in kinds
        import dell_checks
        _docs = {}
        for f_ in dell_checks.DOC_FILES:
            try: _docs[f_] = safe_read(os.path.join(pdir, f_), root=pdir)
            except Exception: pass
        # a binary the shell actually tried to launch must exist on a stock Omarchy install, even if the README documents it
        # (Dell ground truth: voxtype-audio-bridge / cava plugins are BROKEN). FT_DOC_DEPS=1 restores the lenient mode.
        doc_deps = dell_checks.documented_deps(_docs, man) if os.environ.get("FT_DOC_DEPS") else set()   # external tools the README/manifest tells the user to install
        for rel, txt in SENTINELS.items():
            fp = os.path.join(home, rel); os.makedirs(os.path.dirname(fp), exist_ok=True); open(fp, "w").write(txt)
        live = "bar" in kinds and _baseline is not True and not os.environ.get("FT_BAR_BOOT")   # the Dell path: shell running on the stock bar, then `omarchy plugin enable <bar>`
        json.dump(shell_config(None if _baseline is True else pid, kinds, live), open(os.path.join(home, ".config/omarchy/shell.json"), "w"), indent=1)
        install_theme(home)
        before = _snapshot(home)
        rt = os.path.join(S, "rt"); os.makedirs(rt, mode=0o700)
        open(os.path.join(S, "driver.sh"), "w").write(DRIVER)
        summon = any(k in kinds for k in ("panel", "overlay", "menu", "bar-widget")) and not _baseline
        env = dict(ENV_BASE, HOME=home, FT_EXECLOG=os.path.join(S, "exec.log"), XDG_RUNTIME_DIR=rt, FT_DIR=S, FT_ID=pid, QS=QS, FT_SUMMON="1" if summon else "", FT_LIVE_ENABLE="1" if live else "",
                   XDG_CONFIG_HOME=os.path.join(home, ".config"), XDG_CACHE_HOME=os.path.join(home, ".cache"),
                   XDG_DATA_HOME=os.path.join(home, ".local/share"), XDG_STATE_HOME=os.path.join(home, ".local/state"))
        cmd = sandbox_cmd(S, env, ["/bin/bash", os.path.join(S, "driver.sh")])
        t0 = time.time()
        out, timed_out = run_capped(cmd, timeout)
        if timed_out: res["errors"].append("harness timeout (shell hung)")
        res["elapsed"] = round(time.time() - t0, 1)
        stream = {}
        for ln in out.decode("utf-8", "replace").split("\n"):
            tag, _, rest = ln.partition(" ")
            stream.setdefault(tag, []).append(rest)
        log = "\n".join(stream.get("L", []))
        import base64
        for tag, name in (("S0", "shot.png"), ("S1", "shot_after.png")):
            if stream.get(tag):
                try: open(os.path.join(S, name), "wb").write(base64.b64decode("".join(stream[tag])))
                except Exception: pass
        def probe(tag):
            try: return json.loads(stream[tag][-1])
            except Exception: return None
        p0, p1, p2 = probe("P0"), probe("P1"), probe("P2")
        best = dict(p2 or p1 or p0 or {})
        for p in (p0, p1, p2):  # loaders are async: take the most-loaded observation
            if not p: continue
            for k in ("installed", "widgetRegistered", "service", "barLoaded", "open"):
                best[k] = bool(best.get(k)) or bool(p.get(k))
            if p.get("panel") and p["panel"].get("hasItem"): best["panel"] = p["panel"]
            if p.get("bar") and not best.get("bar"): best["bar"] = p["bar"]
            for k in ("widgetTexts", "panelTexts"):
                if p.get(k): best[k] = p[k]
        res["probe"] = best or None
        res["alive"] = bool(stream.get("ALIVE"))
        try:   # USB-D05 runaway memory: RSS growth of the shell between first probe and end of the usage cycle (~9 s)
            m0, m3 = int(stream["M0"][-1].strip()), int(stream["M3"][-1].strip())
            res["rss_kb"] = [m0, m3]; g = (m3 - m0) // 1024
            if g > MEM_FAIL_MB: res["errors"].append(f"runaway memory USB-D05: shell RSS grew {g} MB in ~9 s after the plugin loaded")
            elif g > MEM_WARN_MB: res["soft"].append(f"memory growth USB-D05: shell RSS grew {g} MB in ~9 s")
        except (KeyError, IndexError, ValueError):   # RSS could not be measured: say so instead of silently passing (audit D7)
            res.setdefault("unmeasured", []).append("rss (USB-D05): M0/M3 samples missing from the driver stream")
        if res["alive"] is False and stream.get("U") and stream.get("P2") and not stream.get("P3"):
            res["errors"].append("shell died during the usage cycle USB-D04 (close/reopen via IPC)")
        res["summon"] = (stream.get("SUMMON") or [None])[-1]
        # attribute log lines
        marker = "/plugins/" + os.path.basename(pdir) + "/"
        log = re.sub(r"\x1b\[[0-9;]*m", "", log)
        lines = log.splitlines()
        try:   # index of the first log line written after the usage marker (stdout is one ordered stream)
            raw = out.decode("utf-8", "replace").split("\n"); ui = raw.index("U usage-begin")
            usage_from = sum(1 for x in raw[:ui] if x.startswith("L "))
        except Exception: usage_from = None
        for i, ln in enumerate(lines):
            attributed = marker in ln or re.search(r"(plugin|widget|bar option|summon)\b[^\n]*\b" + re.escape(pid) + r"\b", ln, re.I)
            if not attributed and i > 0 and marker in lines[i - 1] and not re.match(r"^\s*(INFO|WARN|ERROR|DEBUG)", ln): attributed = True
            if not attributed: continue
            s = re.sub(r"file://\S*?/plugins/[^/]+/", "", ln.strip())[:300]
            if usage_from is not None and i >= usage_from: s = "usage: " + s
            if _policy.strict_d9() and "Binding loop detected" in ln: res["errors"].append(s + " (binding loop; strict D9)")
            elif SOFT_PAT.search(ln) or DOWNGRADE.search(ln) or _color_ref(ln, pdir): res["soft"].append(s)
            # the plugin's own console.log/console.info output (DEBUG/INFO level) is never a hard error: the longer
            # USB-D04 usage window started catching graceful "optional file missing" logs (io.github.jondkinney.omapop)
            elif re.match(r"^\s*(DEBUG|INFO)\b", ln): res["soft"].append(s)
            elif PROC_FAIL.search(ln): continue   # judged by the exec checks below (Dell binary list), not by keyword
            elif HARD_ERR.search(ln): res["errors"].append(s)
            elif re.search(r"\b(WARN|ERROR|FATAL|CRIT)", ln) or ERR_PAT.search(ln): res["soft"].append(s)
        if re.search(r"(FATAL|Segmentation|core dumped|qFatal)", log) and not res["alive"]:
            res["errors"].append("shell crashed")
        if not p0 and not p1 and not p2: res["errors"].append("shell did not come up / IPC unreachable")
        res["log_tail"] = [l for l in lines if marker in l][:20]
        execs = parse_exec_log(os.path.join(S, "exec.log"))
        top = [e for e in execs if e["parent"] in TOP_PARENTS]
        if _baseline:
            res["_lines"] = [norm_line(l) for l in lines if l.strip()]
            res["_execs"] = [exec_sig(e["argv"]) for e in top]
            return res
        bl, bx = set(base["lines"]), set(base["execs"])
        if "bar" in kinds: bl |= set(base.get("bar_lines", []))
        plugin_files = set()
        for r_, ds_, fs_ in os.walk(pdir):
            for f_ in fs_: plugin_files.add(os.path.relpath(os.path.join(r_, f_), pdir))
        seen = set()
        def E(msg):
            if msg not in seen: seen.add(msg); res["errors"].append(msg)
        # (a)+(b) commands Quickshell could not start: argv[0] must exist on the Dell; no undefined/null args
        for ln in lines:
            m = PROC_FAIL.search(ln)
            if not m: continue
            argv = re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1))
            if not argv or exec_sig(argv) in bx: continue
            if not resolves(argv[0], plugin_files, pdir) and os.path.basename(argv[0]) in doc_deps:
                res["soft"].append(f"exec: documented external dependency `{argv[0]}` is not installed on the Dell")
            elif not resolves(argv[0], plugin_files, pdir):
                E(f"exec: `{argv[0]}` does not exist on the Dell (Omarchy 4.0.0.alpha bin + system) and is not shipped by the plugin; argv={argv[:6]}")
            else:
                res["soft"].append(f"exec: `{argv[0]}` failed to start in the box (exists on the Dell)")
            bad = [a for a in argv[1:] if BAD_ARG.search(a)]
            if bad: E(f"exec: argv contains undefined/null values {bad[:3]} (argv={argv[:6]})")
        for e in top:
            sig = exec_sig(e["argv"])
            if sig in bx: continue
            argv = e["argv"]
            bad = [a for a in argv[1:] if (BAD_ARG.search(a) if not (len(argv) > 2 and re.match(r"^-\w*c\w*$", argv[1])) else re.search(r"\bundefined\b|\[object Object\]", a))]
            if bad: E(f"exec: argv contains undefined/null values {bad[:3]} (argv={argv[:6]})")
            if len(argv) > 2 and argv[0] in ("sh", "bash", "dash", "zsh") and re.match(r"^-\w*c\w*$", argv[1]) and e["rc"] == "127" \
                    and not re.search(r"\b(command -v|which|type|hash)\b|\[ -[xef] ", argv[2]):   # availability probes / guarded fallbacks are fine
                E(f"exec: `{argv[0]} -c` hit 'command not found' (exit 127) on the Dell PATH: {argv[2][:120]!r}")
        if gap_service:
            hreq = ""
            try: hreq = safe_read(os.path.join(S, "hypr_requests.log"), cap=8_000_000, root=S)
            except Exception: pass
            calls = [" ".join(e["argv"]) for e in execs if e["argv"] and os.path.basename(e["argv"][0]) == "hyprctl"] + hreq.splitlines()
            setters = [c for c in calls if re.search(r"(keyword|eval|BATCH|--batch|hl\.config|setoption)", c) and re.search(r"gaps_(out|in)", c)]
            res["checks"]["gap_setters"] = len(setters)
            if not setters: E("service never changed gaps: no `hyprctl keyword general:gaps_*` (or eval/batch) was issued")
        res["execs"] = [e["argv"][:5] for e in top if exec_sig(e["argv"]) not in bx][:25]
        # (d)/(e) errors that only appear with this plugin installed, even when logged from shell files or console.warn
        for ln in lines:
            if marker in ln or SOFT_PAT.search(ln) or PROC_FAIL.search(ln): continue
            n = norm_line(ln)
            if not n or n in bl: continue
            if DOWNGRADE.search(ln): continue
            if NEW_SHELL_ERR.search(ln) and re.search(r"\b(WARN|ERROR|CRIT|FATAL)\b", ln) and sum(e.startswith("shell broke") for e in res["errors"]) < 8:
                E("shell broke with plugin installed: " + re.sub(r"file://\S*?/shell/", "shell/", ln.strip())[:260])
            elif QML_CONSOLE_ERR.search(ln):
                # hard only when the plugin failed to read something that exists on the Dell (Hyprland/Omarchy surface);
                # graceful "not signed in / no network / not configured" reports about external state are soft
                if DELL_SURFACE.search(ln): E("plugin reported a runtime failure: " + ln.strip()[:260])
                else: res["soft"].append("plugin reported external-state failure: " + ln.strip()[:200])
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
            elif not (g[0].get("width", 0) > 0 and g[0].get("height", 0) > 0):
                # widgets sized from live Hyprland data (workspaces/clients) are empty without real compositor events: unverifiable
                (res["soft"] if hypr_driven else res["errors"]).append(f"bar-widget has zero size {C['widget_slot']}")
            else:   # (f) visible, inside the screen, in the real Dell bar layout
                sw = ((pr.get("screen") or {}).get("w")) or 1920
                x, w = g[0].get("x", 0), g[0].get("width", 0)
                C["widget_x"] = x
                if g[0].get("itemVisible") is False: res["errors"].append("bar-widget item is not visible")
                elif x < 0 or x + w > sw + 1: res["errors"].append(f"bar-widget is outside the screen (x={x}, width={w}, screen={sw})")
            C["panel_opened"] = bool(pr.get("open"))
        texts = (pr.get("widgetTexts") or []) + (pr.get("panelTexts") or [])
        C["texts"] = texts[:12]
        badt = [t for t in texts if BAD_TEXT.search(t)]
        if badt: res["errors"].append(f"renders undefined/null/NaN text: {badt[:3]}")
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
        # pixels: what the user would actually see (real theme, private headless compositor)
        shot = os.path.join(S, "shot.png")
        if os.path.exists(shot):
            try:
                from PIL import Image
                img = Image.open(shot); res["shot"] = shot if keep else None
                if "bar-widget" in kinds and "bar" not in kinds and C.get("widget_slot") and (pr.get("bar") or []) and not any("zero size" in e for e in res["errors"]):
                    g0 = pr["bar"][0]
                    hs = [x.get("height") for x in (pr.get("barGeo") or []) if x.get("visible") and x.get("id") != pid]
                    band = max(set(hs), key=hs.count) if hs else g0["height"]   # bar thickness: clip widgets that overflow the bar
                    n, mx = ink_stats(img, (g0["x"], g0["y"], g0["x"] + g0["width"], g0["y"] + min(g0["height"], band)))
                    C["widget_ink"], C["widget_contrast"] = n, mx
                    if n < 6: res["errors"].append(f"bar-widget draws nothing visible on screen (slot {g0['width']}x{g0['height']} at x={g0['x']}, {n} ink px)")
                    elif mx < MIN_WIDGET_CONTRAST: res["errors"].append(f"bar-widget is illegible on the real theme ({THEME}): max contrast {mx}:1 < {MIN_WIDGET_CONTRAST}:1 (hardcoded colours?)")
                if "bar" in kinds and C.get("bar_active"):
                    W, H = img.width, img.height; t = 48
                    edges = {"top": (0, 0, W, t), "bottom": (0, H - t, W, H), "left": (0, 0, t, H), "right": (W - t, 0, W, H)}
                    ink = {k: ink_stats(img, b) for k, b in edges.items()}
                    C["bar_ink"] = {k: v[0] for k, v in ink.items()}
                    if max(v[0] for v in ink.values()) < 150 and gpu_fx and any(
                            g.get("visible") and g.get("width", 0) > 0 and g.get("height", 0) > 0 for g in (pr.get("barGeo") or [])):
                        # QT_QUICK_BACKEND=software (no GPU/DRM on the box) draws nothing for layer.effect/MultiEffect/ShaderEffect
                        # subtrees; the bar's widgets are laid out with real geometry, so the pixels are unverifiable here, not absent.
                        res["soft"].append(f"bar pixels unverifiable: uses GPU layer effects the software renderer cannot draw (edge ink {C['bar_ink']})")
                    elif max(v[0] for v in ink.values()) < 150:
                        res["errors"].append(f"replacement bar is not visible on screen without fullscreen apps (edge ink {C['bar_ink']})")
            except Exception as e:
                res["soft"].append(f"screenshot analysis failed: {e}")
                res.setdefault("unmeasured", []).append(f"screenshot analysis: {type(e).__name__}")   # audit D7
        # filesystem side effects
        after = _snapshot(home)
        for rel, txt in SENTINELS.items():
            fp = os.path.join(home, rel)
            if not os.path.lexists(fp) or os.path.islink(fp) or safe_read(fp, cap=len(txt) + 1024, root=home) != txt:
                res["soft"].append(f"WARN[high] USB-S01: modified/deleted protected file ~/{rel}")
        bad = [r for r in after if (r not in before or after[r] != before[r]) and not ALLOWED_WRITE.match(r) and r not in SENTINELS]
        for r in bad[:10]: res["soft"].append(f"WARN[medium] USB-S01: wrote outside plugin data dirs: ~/{r}")
        if any(not os.path.exists(os.path.join(home, rel)) for rel in SENTINELS) and sum(not os.path.exists(os.path.join(home, rel)) for rel in SENTINELS) == len(SENTINELS):
            res["errors"].append("DESTRUCTIVE USB-S03: every protected file in ~ was deleted (rm -rf of home)")
        res["writes"] = sorted(r for r in after if (r not in before or after[r] != before[r]) and not r.startswith(".cache/fontconfig"))[:30]
    except Exception as e:
        res["errors"].append(f"harness: {type(e).__name__}: {e}")
    finally:
        if S and not keep: shutil.rmtree(S, ignore_errors=True)
        elif S: res["dir"] = S
    res["pass"] = not res["errors"]
    return res

if __name__ == "__main__":
    import sys
    print(json.dumps(run(src_dir=sys.argv[1], keep="--keep" in sys.argv), indent=1))
