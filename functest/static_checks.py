#!/usr/bin/env python3
"""Static checks for an Omarchy (Quickshell) plugin given as {relpath: text}.
Returns (fails, flags): fails are hard failures, flags are advisory.
Each item is (category, detail)."""
import json, re, os, posixpath

QT6_MODULES = {
    "QtQuick", "QtQuick.Controls", "QtQuick.Controls.Basic", "QtQuick.Controls.Fusion",
    "QtQuick.Controls.Material", "QtQuick.Controls.Universal", "QtQuick.Controls.Imagine",
    "QtQuick.Controls.impl", "QtQuick.Templates", "QtQuick.Layouts", "QtQuick.Window", "QtQuick.Effects",
    "QtQuick.Shapes", "QtQuick.Particles", "QtQuick.Dialogs", "QtQuick.LocalStorage", "QtQuick.VectorImage",
    "QtQuick.Pdf",
    "QtQml", "QtQml.Models", "QtQml.WorkerScript", "QtCore", "QtMultimedia", "QtPositioning", "QtLocation",
    "Qt5Compat.GraphicalEffects", "Qt.labs.platform", "Qt.labs.folderlistmodel", "Qt.labs.settings",
    "Qt.labs.qmlmodels", "Qt.labs.animation", "Qt.labs.sharedimage", "Qt.labs.wavefrontmesh", "QtTest",
    "QtWebSockets", "QtSvg",
}
QS_MODULES = set("""Quickshell Quickshell.Bluetooth Quickshell.DBusMenu Quickshell.Hyprland Quickshell.I3
Quickshell.Io Quickshell.Networking Quickshell.Services.Greetd Quickshell.Services.Mpris
Quickshell.Services.Notifications Quickshell.Services.Pam Quickshell.Services.Pipewire Quickshell.Services.Polkit
Quickshell.Services.SystemTray Quickshell.Services.UPower Quickshell.Wayland Quickshell.Widgets
Quickshell.WindowManager Quickshell.X11""".split())
OMARCHY_MODULES = {"qs.Commons", "qs.Ui"}   # the only Omarchy-provided QML modules (shell/Commons, shell/Ui qmldir)
QT5_ONLY = {"QtGraphicalEffects": "Qt5 QtGraphicalEffects (Qt6 = Qt5Compat.GraphicalEffects / QtQuick.Effects)",
            "QtQuick.Controls.Styles": "Qt5-only Controls 1 styles", "QtQuick.Extras": "Qt5-only QtQuick.Extras",
            "QtQuick.PrivateWidgets": "Qt5-only", "QtQuick.Dialogs.qml": "Qt5-only", "QtWebKit": "Qt5-only"}

ALLOWED_ENTRY_EXT = (".qml",)
IMPORT_RE = re.compile(r'^\s*import\s+([^\s;]+)(?:\s+([\d.]+))?(?:\s+as\s+\w+)?', re.M)

# JS / Node / browser / fake-host idioms that cannot exist in a Quickshell QML runtime
JS_FAKE = [
    (r"^(?!.*typeof\s+require).*\brequire\s*\(\s*['\"]", "node require()"), (r"\bchild_process\b", "node child_process"),
    (r"^\s*import\s+[\w{}*,\s]+\s+from\s+['\"]", "ES module import"), (r"^(?!.*typeof\s+module)\s*module\.exports\b", "CommonJS exports"),
    (r"\bdocument\.(getElementById|querySelector|createElement|body)", "browser DOM"),
    (r"\bwindow\.(addEventListener|localStorage)", "browser window API"), (r"\bprocess\.env\b", "node process.env"),
    (r"\bQNetworkAccessManager\b|\bQProcess\b|\bQFile\b|\bQTimer\b", "C++ Qt class used from QML/JS"),
    (r"\bimport\s+omarchy\b|\bfrom\s+['\"]omarchy['\"]|\bOmarchy\.(api|shell|notify|exec|register)", "made-up omarchy JS/QML API"),
    (r"\bQuickshell\.clipboard\b", "Quickshell.clipboard is not a real API"),
    (r"\bStyle\.font\.size\s*\(", "Style.font.size() is not a real API"),
    (r"\bfetch\s*\(\s*['\"`]http", "browser fetch()"),
]
# Shell-out / write danger: target paths
DANGER_PATHS = r"(\.config/hypr\b|/etc/|/usr/(lib|share|local|include)/|/boot/|/var/(lib|log)/|\.bashrc|\.zshrc|\.profile\b|\.config/omarchy/(current|themes|hooks)|\.local/share/omarchy|/sys/|/dev/sd)"
WRITE_VERBS = r"(>>?|\btee\b|\bcp\b|\bmv\b|\brm\b|\bsed\s+-i|\bln\s+-s|\bdd\b|\bchmod\b|\bchown\b|\binstall\b|\btruncate\b|setText|write_text|writeFile|open\([^)]*['\"][wa]\+?['\"])"
DANGER_CMDS = [(r"curl[^\n|]*\|\s*(ba|z)?sh\b|wget[^\n|]*\|\s*(ba|z)?sh\b", "curl|sh"),
               (r"\brm\s+-rf?\s+(~|\$HOME|/)(\s|$|['\"])", "rm -rf of home/root"),
]
FAKE_DATA = [(r"[\"']Item [1-3][\"']", "'Item 1/2/3' placeholder data"), (r"[Ll]orem ipsum", "lorem ipsum"),
             (r"[\"']John Doe[\"']|[\"']Jane Doe[\"']", "fake person"), (r"\bfoo\b.*\bbar\b.*\bbaz\b", "foo/bar/baz"),
             (r"Math\.random\(\)\s*\*\s*\d+.*(speed|usage|percent|temp|cpu|mbps|download|upload)", "random numbers as data"),
             (r"(speed|usage|percent|temp|cpu|mbps|download|upload)\w*[^\n]{0,40}Math\.random\(\)", "random numbers as data"),
             (r"\b(TODO|FIXME)\b[^\n]*(implement|real|actual|replace)", "TODO stub")]
HANDLER_RE = re.compile(r'\b(on[A-Z]\w*)\s*:\s*(\{\s*\}|\{\s*(console\.(log|debug|info)\([^)]*\)\s*;?\s*)+\}|console\.(log|debug|info)\([^)]*\)\s*;?\s*$)', re.M)
ANY_HANDLER_RE = re.compile(r'\b(onClicked|onPressed|onReleased|onTriggered|onActivated|onAccepted|onToggled|onTapped|onCheckedChanged|onExited|onStreamFinished|onRead|onTextChanged)\s*:', re.M)
EMPTY_FUNC_RE = re.compile(r'\bfunction\s+(\w+)\s*\([^)]*\)\s*\{\s*(//[^\n]*\s*)*\}')

def strip_comments(s):
    s = re.sub(r'/\*.*?\*/', '', s, flags=re.S)
    return re.sub(r'(^|[^:"\'])//[^\n]*', r'\1', s)

def check(files):
    fails, flags = [], []
    F = lambda c, d: fails.append((c, d))
    W = lambda c, d: flags.append((c, d))
    man = None
    if "manifest.json" in files:
        try: man = json.loads(files["manifest.json"])
        except Exception: F("manifest", "manifest.json not JSON")
    eps = (man or {}).get("entryPoints") if isinstance(man, dict) else None
    if isinstance(eps, dict):
        for k, v in eps.items():
            if isinstance(v, str) and not v.endswith(ALLOWED_ENTRY_EXT):
                F("entry-not-qml", f"entryPoints.{k} = {v} (Quickshell loads QML only)")
    qml = {p: c for p, c in files.items() if p.endswith(".qml")}
    js = {p: c for p, c in files.items() if p.endswith((".js", ".mjs", ".ts"))}
    if man and not qml: F("no-qml", "plugin contains no QML file")
    dirs = {posixpath.dirname(p) for p in files}
    ep_set = set(v for v in (eps or {}).values() if isinstance(v, str)) if isinstance(eps, dict) else set()
    qml_js = set()
    for p, c in qml.items():
        for m in re.finditer(r'^\s*import\s+"([^"]+\.m?js)"', c, re.M):
            qml_js.add(posixpath.normpath(posixpath.join(posixpath.dirname(p), m.group(1))))
    for p, c in js.items():
        for m in re.finditer(r'^\s*\.import\s+"([^"]+\.m?js)"', c, re.M):
            qml_js.add(posixpath.normpath(posixpath.join(posixpath.dirname(p), m.group(1))))
    for p, c in {**qml, **js}.items():
        body = strip_comments(c)
        if p.endswith(".qml"):
            for m in IMPORT_RE.finditer(body):
                mod, ver = m.group(1), m.group(2)
                if mod.startswith('"'):
                    rel = mod.strip('"')
                    tgt = posixpath.normpath(posixpath.join(posixpath.dirname(p), rel))
                    if rel.endswith(".js") or rel.endswith(".qml"):
                        if tgt not in files and not files.get("__tree_has__", {}).get(tgt): F("bad-import", f"{p}: relative import {rel} missing")
                    continue
                if mod in QT5_ONLY: F("qt5-api", f"{p}: import {mod} — {QT5_ONLY[mod]}"); continue
                if mod in QT6_MODULES or mod in QS_MODULES or mod in OMARCHY_MODULES: 
                    if ver and ver.split(".")[0] == "1" and mod.startswith("QtQuick.Controls"): F("qt5-api", f"{p}: QtQuick.Controls 1.x")
                    continue
                if mod.startswith("qs."): F("bad-import", f"{p}: qs.{mod[3:]} is not an Omarchy module (only qs.Commons, qs.Ui)")
                elif mod.startswith("Quickshell"): F("bad-import", f"{p}: Quickshell module {mod} does not exist")
                elif mod[0].isupper() or mod.startswith("org.") : F("bad-import", f"{p}: unknown module {mod}")
                else: F("bad-import", f"{p}: unknown module {mod}")
            if re.search(r'\.pragma\s+library', body) is None and re.search(r'\bComponent\.onCompleted\s*:\s*\{[^}]*\bTimer\s*\{', body, re.S):
                F("qml-syntax", f"{p}: QML object declared inside JS block")
            if re.search(r'\bQtObject\s*\{[^{}]*\b(Timer|FileView|Process)\s*\{', body):
                W("footgun", f"{p}: QtObject hosting Timer/FileView/Process")
            for m in re.finditer(r'Style\.font\.(title|subtitle|display|heading)\b', body):
                W("footgun", f"{p}: Style.font.{m.group(1)} is VPS-unsafe"); break
        if p in js and p not in ep_set and p not in qml_js:
            continue  # JS not loaded by the shell (node tests, tool hooks): out of scope
        guarded = p in js and re.search(r"typeof\s+(module|require|process)\s*[!=]==?", body)
        for pat, what in JS_FAKE:
            if guarded and what in ("node require()", "CommonJS exports", "node process.env"): continue
            if re.search(pat, body, re.M): F("fake-api", f"{p}: {what}")
    # danger: scan all text files (qml/js/sh/py)
    for p, c in files.items():
        if p == "manifest.json" or p.endswith((".md", ".txt", ".json", ".svg")): continue
        body = strip_comments(c) if p.endswith((".qml", ".js")) else re.sub(r'(^|\s)#[^\n!]*', r'\1', c)
        for line in body.splitlines():
            if re.match(r"^\s*(local\s+|export\s+)?[A-Za-z_]\w*=['\"]", line): continue  # text assigned to a var (hint/fix copy), not executed here
            if re.search(r">>?\s*['\"]?[^\s'\"]*" + DANGER_PATHS, line) or \
               re.search(r"\b(tee(\s+-a)?|cp|mv|sed\s+-i\S*|ln\s+-s\S*|rm(\s+-\w+)?|install|dd|truncate|chmod|chown)\b[^|;&\n]*" + DANGER_PATHS, line) or \
               re.search(r"(setText|writeFile|writeFileSync|write_text|open\([^)]*['\"][wa]\+?['\"])[^\n]*" + DANGER_PATHS, line) or \
               re.search(DANGER_PATHS + r"[^\n]*(write_text|open\([^)]*['\"][wa]\+?['\"])", line):
                F("dangerous-write", f"{p}: {line.strip()[:140]}")
        lits = re.findall(r"['\"`]([^'\"`\n]*)['\"`]", body)
        dlits = [l for l in lits if re.search(r"(\.config/hypr/|^/etc/|\.bashrc|\.zshrc)", l)]
        if re.search(r"\.config/omarchy/shell\.json", body) and re.search(r"(setText|>\s*\S*shell\.json|writeFile)", body):
            W("writes-shell-json", f"{p}: writes ~/.config/omarchy/shell.json directly (prefer omarchy-shell IPC)")
        if dlits and re.search(r"\b(exec|execSync|spawn|execDetached|Process|command\s*:)\b", body) and \
           re.search(r"(>>?\s*\$?\{?\w|\bcp\b|\bmv\b|\bsed\s+-i|\btee\b|setText|writeFile|write_text|\brm\b)", body):
            F("dangerous-write", f"{p}: writes/shell-outs alongside protected path {dlits[0][:80]}")
        if re.search(r"[\"'](sudo|pkexec)[\"']\s*,|\bexec\w*\([\"'`](sudo|pkexec)\b", body): F("dangerous-cmd", f"{p}: runs sudo/pkexec")
        for pat, what in DANGER_CMDS:
            if re.search(pat, body): F("dangerous-cmd", f"{p}: {what}")
        # FileView.setText to a path we can see in the same object that isn't a plugin data dir
        for m in re.finditer(r'FileView\s*\{(.{0,600}?)\}', body, re.S):
            blk = m.group(1)
            pm = re.search(r'\bpath\s*:\s*([^\n]+)', blk)
            if pm and re.search(DANGER_PATHS, pm.group(1)) and ("setText" in body or "blockWrites: false" in blk):
                F("dangerous-write", f"{p}: FileView writes {pm.group(1).strip()[:100]}")
    for p, c in qml.items():
        m = re.search(r'^\s*(ApplicationWindow|Window)\s*\{', strip_comments(c), re.M)
        if m and isinstance(eps, dict) and p in eps.values():
            F("not-shell-surface", f"{p}: entry root is {m.group(1)} (desktop app window, not a Quickshell/Omarchy surface)")
    # placeholder / no-op UI
    allq = "\n".join(strip_comments(c) for c in qml.values())
    noop = HANDLER_RE.findall(allq)
    handlers = ANY_HANDLER_RE.findall(allq)
    emptyf = [n[0] for n in EMPTY_FUNC_RE.findall(allq) if n[0] not in ("open", "close", "toggle", "closeForPopoutSwitch")]
    if qml:
        real = max(0, len(handlers) - len([h for h in noop if h[0] in ANY_HANDLER_RE.pattern]))
        if noop and real == 0: F("placeholder-ui", f"all {len(noop)} UI handlers are empty/console.log no-ops: {', '.join(sorted({h[0] for h in noop}))}")
        elif noop: W("placeholder-ui", f"{len(noop)} no-op handler(s): {', '.join(sorted({h[0] for h in noop}))}")
        hl = "\n".join(re.findall(r"\bon[A-Z]\w*\s*:[^\n]*", allq))
        called = [n for n in emptyf if re.search(r"\b" + re.escape(n) + r"\s*\(", hl)]
        if called: F("placeholder-ui", f"UI handlers call empty function(s): {', '.join(called[:6])}")
        elif emptyf: W("placeholder-ui", f"empty function(s): {', '.join(emptyf[:4])}")
    if qml and man:
        loc = sum(1 for l in allq.splitlines() if l.strip() and l.strip() not in "{}")
        live = re.search(r"\b(Process|Timer|FileView|Connections|IpcHandler|SplitParser|StdioCollector|Mpris|Pipewire|UPower|SystemTray|Hyprland|NotificationServer|ListModel|Repeater|ListView|MouseArea|WidgetButton|onClicked|TextField|execDetached)\b", allq)
        if loc < 40 and not live: F("placeholder-ui", f"trivial plugin: {loc} QML lines, no IO, data or interaction")
    for pat, what in FAKE_DATA:
        if re.search(pat, allq): F("fake-data", what)
    # dedupe
    def dd(xs):
        seen, out = set(), []
        for x in xs:
            if x not in seen: seen.add(x); out.append(x)
        return out
    return dd(fails), dd(flags)

if __name__ == "__main__":
    import sys
    d = sys.argv[1]; files = {}
    for r, ds, fs in os.walk(d):
        ds[:] = [x for x in ds if x not in (".git", "node_modules", "tests", "test", "__pycache__")]
        for f in fs:
            p = os.path.relpath(os.path.join(r, f), d)
            try: files[p] = open(os.path.join(r, f), encoding="utf-8").read()
            except Exception: pass
    fa, fl = check(files)
    print(json.dumps({"fails": fa, "flags": fl}, indent=1))
