#!/usr/bin/env python3
"""Usuba Checker: hardening checks layered on the functest (see functest/STANDARD.md for the rule ids).
check(files) -> list of findings: dict(rule, severity, file, reason, hint).
severity: "error" (always blocking), "high" (heuristic, blocking), "medium"/"low" (heuristic, advisory)."""
import json, os, re, posixpath, sys, functools
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "dell_env"))
from binaries import resolves, KNOWN
STANDARD = "Usuba Standard v0.1 (Omarchy 4.0.4)"
T = json.load(open(os.path.join(HERE, "types.json")))
COMPS, MODS = T["comps"], T["modules"]

# ---------------------------------------------------------------- text helpers
def sanitize(s):
    """Blank out comments and string contents (keeping offsets and quote chars)."""
    out, i, n = list(s), 0, len(s)
    while i < n:
        c = s[i]
        if c == "/" and s.startswith("//", i):
            j = s.find("\n", i); j = n if j < 0 else j
            for k in range(i, j): out[k] = " "
            i = j; continue
        if c == "/" and s.startswith("/*", i):
            j = s.find("*/", i + 2); j = n if j < 0 else j + 2
            for k in range(i, j):
                if s[k] != "\n": out[k] = " "
            i = j; continue
        if c == "/" and _regex_start(s, i):
            j, cls = i + 1, False
            while j < n and s[j] != "\n":
                if s[j] == "\\": j += 2; continue
                if s[j] == "[": cls = True
                elif s[j] == "]": cls = False
                elif s[j] == "/" and not cls: break
                j += 1
            if j < n and s[j] == "/":
                for k in range(i + 1, j): out[k] = " "
                i = j + 1; continue
        if c in "\"'`":
            j = i + 1
            while j < n and s[j] != c:
                if s[j] == "\\": j += 1
                elif c != "`" and s[j] == "\n": break
                j += 1
            for k in range(i + 1, min(j, n)):
                if s[k] != "\n": out[k] = " "
            i = j + 1; continue
        i += 1
    return "".join(out)

def _regex_start(s, i):
    k = i - 1
    while k >= 0 and s[k] in " \t": k -= 1
    if k < 0: return False
    if s[k] in "(,=:[!&|?{};\n": return not s.startswith("//", i) and not s.startswith("/*", i)
    return s[max(0, k - 5):k + 1].endswith("return")

def strip_comments_keep_strings(s):
    san = sanitize(s)
    return "".join(c if (san[k] != " " or c in " \t\n") or k > 0 and _in_string(san, k) else " " for k, c in enumerate(s)) if False else _cks(s)

def _cks(s):
    out, i, n = list(s), 0, len(s)
    while i < n:
        c = s[i]
        if c == "/" and s.startswith("//", i) and (i == 0 or s[i-1] != ":"):
            j = s.find("\n", i); j = n if j < 0 else j
            for k in range(i, j): out[k] = " "
            i = j; continue
        if c == "/" and s.startswith("/*", i):
            j = s.find("*/", i + 2); j = n if j < 0 else j + 2
            for k in range(i, j):
                if s[k] != "\n": out[k] = " "
            i = j; continue
        if c in "\"'`":
            j = i + 1
            while j < n and s[j] != c:
                if s[j] == "\\": j += 1
                elif c != "`" and s[j] == "\n": break
                j += 1
            i = j + 1; continue
        i += 1
    return "".join(out)

def match_brace(san, i):
    d = 0
    for j in range(i, len(san)):
        if san[j] == "{": d += 1
        elif san[j] == "}":
            d -= 1
            if d == 0: return j
    return len(san)

def lineno(s, i): return s.count("\n", 0, i) + 1

# ---------------------------------------------------------------- type environment
@functools.lru_cache(None)
def module_types(mod, depth=0):
    M = MODS.get(mod)
    if M is None: return None
    out = dict(M["types"])
    if depth < 4:
        for im in M["imports"]:
            if im == "auto": continue
            sub = module_types(im, depth + 1)
            if sub: out = {**sub, **out}
    if mod.startswith("QtQuick") and mod != "QtQml":
        q = module_types("QtQml", depth + 1) or {}
        out = {**q, **out}
    return out

ALL_TYPE_HOMES = {}
for m, M in MODS.items():
    for t in M["types"]: ALL_TYPE_HOMES.setdefault(t, []).append(m)

def comp_chain(cpp):
    seen, out = set(), []
    while cpp and cpp not in seen and cpp in COMPS:
        seen.add(cpp); out.append(COMPS[cpp]); cpp = COMPS[cpp]["proto"]
    complete = not cpp or cpp in ("QObject",) or cpp in COMPS
    if cpp == "QObject" and "QObject" in COMPS: pass
    return out, (cpp is None or cpp in seen or cpp in COMPS)

def members_of(tdef, env, depth=0):
    """(signals, props, methods, complete) for a resolved type definition."""
    sig, props, meth = set(), set(), set()
    if isinstance(tdef, str):
        chain, complete = comp_chain(tdef)
        for c in chain: sig |= set(c["signals"]); props |= set(c["props"]); meth |= set(c["methods"])
        return sig, props, meth, complete
    if isinstance(tdef, dict) and tdef.get("local") and depth < 6:
        f = tdef["local"]; body = _FILES.get(f, "")
        lm = local_members(_FILES, f)
        env2, al2, ow2 = file_env(f, body, _FILES)
        sig |= set(lm["qml"]); props |= set(lm["qml"]); meth |= set(lm["qml"])
        rt = lm["root"]
        if not rt: return sig, props, meth, True
        sub = resolve(rt, env2, al2) if rt != posixpath.basename(f)[:-4] else env2["__modenv__"].get(rt)
        if sub is None: return sig, props, meth, False
        s2, p2, m2, c2 = members_of(sub, env2, depth + 1)
        return sig | s2, props | p2, meth | m2, c2
    if isinstance(tdef, dict) and "qml" in tdef:
        mem = set(tdef["qml"]); sig |= mem; props |= mem; meth |= mem
        rt = tdef.get("root")
        if rt and depth < 6:
            menv = env.get("__modenv__", env)
            sub = menv.get(rt) or (module_types("QtQuick") or {}).get(rt) or (module_types("Quickshell") or {}).get(rt)
            if sub is None and "." in rt:
                sub = (module_types("QtQuick.Templates") or {}).get(rt.split(".")[-1]) or (module_types("Quickshell") or {}).get(rt.split(".")[-1])
            if sub is None: return sig, props, meth, False
            s2, p2, m2, c2 = members_of(sub, env, depth + 1)
            return sig | s2, props | p2, meth | m2, c2
        return sig, props, meth, rt is None
    return sig, props, meth, False

IMPORT_RE = re.compile(r'^\s*import\s+("?[^\s;"]+"?)(?:\s+[\d.]+)?(?:\s+as\s+(\w+))?', re.M)
def file_env(path, body, files):
    """Types visible in a QML file. Returns (env, aliases, open_world)."""
    env, aliases, open_world = {}, {}, False
    for m in IMPORT_RE.finditer(body):
        mod, alias = m.group(1), m.group(2)
        if mod.startswith('"'):
            rel = mod.strip('"')
            if rel.endswith((".js", ".mjs")):
                if alias: aliases[alias] = {"__js__": True}
                continue
            d = posixpath.normpath(posixpath.join(posixpath.dirname(path), rel))
            if d == ".": d = ""
            dt = {posixpath.basename(f)[:-4]: {"qml": [], "root": None, "local": f} for f in files if f.endswith(".qml") and posixpath.dirname(f) == d}
            qd = files.get(posixpath.join(d, "qmldir"), "") if d else files.get("qmldir", "")
            for line in qd.splitlines():
                w = line.split()
                if len(w) >= 2 and w[-1].endswith(".qml"):
                    nm = w[1] if w[0] == "singleton" else w[0]
                    tgt = posixpath.normpath(posixpath.join(d, w[-1]))
                    if nm[:1].isupper() and tgt in files: dt[nm] = {"qml": [], "root": None, "local": tgt, "singleton": w[0] == "singleton"}
            if alias: aliases[alias] = dt
            else: env.update(dt)
            continue
        mt = module_types(mod)
        if mt is None: open_world = True; continue
        if alias: aliases[alias] = mt
        else: env.update(mt)
    env.update(module_types("QtQml") or {})
    for nm in re.findall(r"^\s*component\s+(\w+)\s*:", sanitize(body), re.M):
        env[nm] = {"qml": [], "root": None, "inline": True}
    # same-directory QML files are implicitly importable (Omarchy loads plugins from their directory)
    d = posixpath.dirname(path)
    modenv = dict(env)
    for f in files:
        if f.endswith(".qml") and posixpath.dirname(f) == d and f != path:
            n = posixpath.basename(f)[:-4]
            if n[:1].isupper(): env[n] = {"qml": [], "root": None, "local": f}
    env["__modenv__"] = modenv
    return env, aliases, open_world

def resolve(tname, env, aliases):
    if "." in tname:
        a, b = tname.split(".", 1)
        if a in aliases: return aliases[a].get(b)
        return None
    return env.get(tname)

def local_members(files, f):
    """members of a plugin-local QML type, computed lazily."""
    s = sanitize(files.get(f, ""))
    mem = set(re.findall(r"\bproperty\s+[\w.<>]+\s+(\w+)", s)) | set(re.findall(r"\bfunction\s+(\w+)", s)) | set(re.findall(r"\bsignal\s+(\w+)", s))
    rt = re.search(r"^\s*([A-Z][\w.]*)\s*\{", re.sub(r"^\s*(import|pragma)[^\n]*", "", s, flags=re.M), re.M)
    return {"qml": sorted(mem), "root": rt.group(1) if rt else None}

# ---------------------------------------------------------------- QML object scan
OBJ_RE = re.compile(r'(^|[:\[,]|\bon\b)\s*([A-Z]\w*(?:\.[A-Z]\w*)?)(\s+on\s+[\w.]+)?\s*\{', re.M)
def qml_objects(san):
    objs = []
    for m in OBJ_RE.finditer(san):
        pre = san[:m.start(2)].rstrip()
        if pre.endswith(("(", "=", "return", "?", "&&", "||")): continue
        lb = san.index("{", m.end(2)); rb = match_brace(san, lb)
        objs.append(dict(type=m.group(2), start=m.start(2), lb=lb, rb=rb))
    return objs

def direct_children(san, lb, rb):
    """(offset, line) pairs of the object body with nested {...} blanked, so only depth-1 members remain"""
    seg = list(san[lb + 1:rb]); d = 0
    for k, ch in enumerate(seg):
        if ch == "{": d += 1; continue
        if ch == "}": d -= 1; continue
        if d > 0 and ch != "\n": seg[k] = " "
    out, pos = [], lb + 1
    for ln in "".join(seg).split("\n"):
        out.append((pos, ln)); pos += len(ln) + 1
    return out

def _old_direct_children(san, lb, rb):
    """yield (offset, text) of lines at depth 1 inside an object body"""
    d, i, out, line_start = 0, lb, [], None
    seg = san[lb:rb + 1]
    depth = 0; pos = 0
    for ln in seg.split("\n"):
        if depth == 1: out.append((lb + pos, ln))
        depth += ln.count("{") - ln.count("}")
        pos += len(ln) + 1
    # first line (after the opening brace) may hold inline children: "Foo { onX: y }"
    return out

JS_GLOBALS = set("""Math JSON Date Object Array String Number Boolean Promise RegExp Error TypeError RangeError Map Set WeakMap
Symbol Infinity NaN Intl ArrayBuffer Uint8Array Int32Array Float32Array DataView Reflect Proxy BigInt XMLHttpRequest Qt
Quickshell console parseInt parseFloat isNaN isFinite encodeURIComponent decodeURIComponent encodeURI decodeURI escape unescape
undefined null true false print gc qsTr qsTranslate qsTrId QT_TR_NOOP""".split())
JS_NEW_OK = JS_GLOBALS | {"Function", "URL", "Uint16Array", "Int8Array", "Int16Array", "Uint32Array", "Float64Array", "TextDecoder", "TextEncoder"}
QT_GLOBAL = set("""application platform inputMethod styleHints uiLanguage atob btoa binding callLater colorEqual createComponent
createQmlObject darker exit font fontFamilies formatDate formatDateTime formatTime hsla hsva include isQtObject lighter locale md5
matrix4x4 openUrlExternally point quaternion quit rect resolvedUrl rgba size tint vector2d vector3d vector4d url alpha color
enumStringToValue enumValueToString enumValueToStrings enumStringsToValue rgb""".split())
QS_SINGLETON = None
def qs_members():
    global QS_SINGLETON
    if QS_SINGLETON is None:
        cpp = MODS["Quickshell"]["types"].get("Quickshell")
        s, p, m, _ = members_of(cpp, {}) if cpp else (set(), set(), set(), True)
        QS_SINGLETON = s | p | m
    return QS_SINGLETON

INVENTED = [  # (regex, what, hint) known hallucinations that must never pass, kept as a safety net behind the allowlist
    (r"\bQuickshell\.exec\s*\(", "Quickshell.exec() does not exist (there is no promise-returning exec)", "use a `Process { command: [...]; stdout: StdioCollector { onStreamFinished: ... } }` and set `running = true`, or `Quickshell.execDetached([...])` for fire-and-forget"),
    (r"\bQt\.clipboard\b", "Qt.clipboard does not exist in QML", "read with `Process { command: [\"wl-paste\", \"-n\"] }` and write with `Quickshell.execDetached([\"wl-copy\", text])`"),
    (r"\bService\.call\s*\(", "Service.call() is not an Omarchy/Quickshell API", "call another plugin through `omarchy-shell` IPC (`Quickshell.execDetached([\"omarchy-shell\", ...])`) or an `IpcHandler`"),
    (r"\bnew\s+(Sequential|Parallel|Number|Property|Color)Animation\s*\(", "QML animations cannot be constructed with `new` in JavaScript", "declare the animation as a QML object with an id and call `anim.start()`"),
]
X11_TOOLS = {"xinput": "use `hyprctl keyword device[...]:enabled` / `hyprctl devices`", "setxkbmap": "use `hyprctl switchxkblayout` or `hyprctl keyword input:kb_layout`",
             "onboard": "use a Wayland on-screen keyboard (e.g. wvkbd / squeekboard), shipped or documented as a dependency",
             "xdotool": "use `wtype` (installed) or `hyprctl dispatch`", "xrandr": "use `hyprctl monitors` / `hyprctl keyword monitor`",
             "xclip": "use `wl-copy` / `wl-paste`", "xsel": "use `wl-copy` / `wl-paste`", "xprop": "use `hyprctl activewindow -j`",
             "wmctrl": "use `hyprctl clients -j` / `hyprctl dispatch`", "xset": "use `hyprctl dispatch dpms` / hypridle", "xmodmap": "use Hyprland `input:kb_options`",
             "xbacklight": "use `brightnessctl`", "xev": "use `wev`", "xkill": "use `hyprctl kill`", "xwininfo": "use `hyprctl clients -j`"}
HYPRCTL_SUB = set("""activewindow activeworkspace animations binds clients configerrors cursorpos decorations devices dismissnotify dispatch
getoption globalshortcuts hyprpaper hyprsunset instances keyword kill layers layouts monitors notify plugin reload rollinglog setcursor
seterror setprop splash repl switchxkblayout systeminfo version workspacerules workspaces submap output eval reloadshaders getprop""".split())
HYPRSUNSET_IPC = {"temperature", "identity", "gamma", "reset"}
SH_WORDS = set("""if then else elif fi for while until do done case esac in function select time exec eval set export unset local
readonly declare typeset source . cd test [ [[ ] ]] echo printf read return exit break continue shift trap wait true false command builtin
type hash alias let getopts pushd popd umask ulimit shopt kill { } ! : pwd mapfile readarray disown bg fg jobs coproc compgen complete
elif esac""".split())

def str_lits(s):
    return [(m.start(), next((g for g in m.groups() if g is not None), "")) for m in _LIT.finditer(s)]
_LIT = re.compile(r"\"((?:[^\"\\\n]|\\.)*)\"|'((?:[^'\\\n]|\\.)*)'|`((?:[^`\\]|\\.)*)`")

def argv_arrays(raw, lang):
    """Yield (offset, [literal-or-None,...]) for command argv arrays in QML/JS/Python source."""
    pats = [r"\bcommand\s*[:=]\s*\[", r"\bexec(?:Detached)?\s*\(\s*(?:\{\s*command\s*:\s*)?\[", r"\bstartDetached\s*\(\s*\["]
    if lang == "py": pats = [r"\bsubprocess\.\w+\(\s*\[", r"\bos\.exec\w*\([^,\n]*,\s*\[", r"\b_?run\w*\(\s*\[", r"\bPopen\(\s*\["]
    san = sanitize(raw)
    for pat in pats:
        for m in re.finditer(pat, san):
            lb = m.end() - 1; d = 0; j = lb
            while j < len(san):
                if san[j] in "[(": d += 1
                elif san[j] in "])":
                    d -= 1
                    if d == 0: break
                j += 1
            inner_raw = raw[lb + 1:j]; inner_san = san[lb + 1:j]
            parts, k, depth, start = [], 0, 0, 0
            for k, ch in enumerate(inner_san + ","):
                if ch in "([{": depth += 1
                elif ch in ")]}": depth -= 1
                elif ch == "," and depth == 0:
                    piece = inner_raw[start:k].strip()
                    lm = re.fullmatch(r"(['\"`])((?:\\.|(?!\1).)*)\1", piece, re.S)
                    parts.append(lm.group(2) if lm and "${" not in lm.group(2) else (lm.group(2) if lm else None))
                    start = k + 1
            if parts and parts[-1] == "": parts.pop()
            yield m.start(), parts

WAYLAND_ALT = ("wl-copy", "wl-paste", "wtype", "hyprctl", "ydotool", "brightnessctl", "wvkbd", "squeekboard")
def guarded_words(script):
    """tools probed with `command -v` / `which` / `type` / `hash` - optional fallbacks, not hard requirements"""
    return set(re.findall(r"\b(?:command\s+-v|which|type\s+-[pP]|hash)\s+([\w.+-]+)", script))

def shell_words(script):
    """first words of each simple command in a shell string; also returns (word, rest) pairs."""
    s = re.sub(r"\$\{[^}]*\}", "X", script)
    s = re.sub(r"'[^']*'", "''", s)
    s = re.sub(r'"[^"$`]*"', '""', s)
    s = re.sub(r"\(\((.|\n)*?\)\)", " ", s)
    s = re.sub(r"\[\[[^\n]*?\]\]", " ", s)
    s = re.sub(r"(?m)^\s*[^()\s;]+\)\s", " ; ", s)            # case labels  `ctrl) ...`
    funcs = set(re.findall(r"(?m)^\s*(?:function\s+)?([A-Za-z_][\w-]*)\s*\(\s*\)", s)) | set(re.findall(r"\bfunction\s+([\w-]+)", s))
    s = re.sub(r"(?m)^\s*(?:function\s+)?[A-Za-z_][\w-]*\s*\(\s*\)", " ", s)
    out = []
    for seg in re.split(r"\|\||&&|[;|&\n`]|\$\(|\(|\)|\bthen\b|\bdo\b|\belse\b", s):
        toks = seg.strip().split()
        while toks and (re.match(r"^[A-Za-z_]\w*=", toks[0]) or toks[0] in ("sudo", "exec", "nohup", "setsid", "env", "timeout", "nice", "command", "!", "{", "time", "uwsm-app", "--") or re.match(r"^\d+(\.\d+)?[smh]?$", toks[0]) or toks[0].startswith("-")):
            if toks[0] in ("timeout",) and len(toks) > 1 and re.match(r"^-", toks[1]): toks = toks[1:]
            toks = toks[1:]
        if not toks: continue
        w = toks[0].strip("\"'")
        if len(toks) > 1 and toks[1].startswith(("=", "+=", "(")): continue
        if "/" not in w and not re.match(r"^[a-z0-9][a-z0-9_+-]*$", w): continue
        if not w or w in SH_WORDS or w in funcs or w.isupper() or w.startswith(("$", "~", "<", ">", "#", "[", "-")) or re.match(r"^\d", w) or not re.match(r"^[\w./+-]+$", w): continue
        out.append((w, toks[1:]))
    return out

# ---------------------------------------------------------------- main check
import threading
class _TL(threading.local):
    files = {}
_tl = _TL()
class _FilesProxy:
    def get(self, k, d=None): return _tl.files.get(k, d)
    def __iter__(self): return iter(_tl.files)
    def __contains__(self, k): return k in _tl.files
    def __getitem__(self, k): return _tl.files[k]
_FILES = _FilesProxy()
def check(files, man=None):
    _tl.files = files
    finds = []
    def add(rule, sev, f, reason, hint):
        finds.append(dict(rule=rule, severity=sev, file=f, reason=reason, hint=hint))
    if man is None:
        try: man = json.loads(files.get("manifest.json", ""))
        except Exception: man = {}
    if not isinstance(man, dict): man = {}
    shipped = set(files)
    shipped_base = {posixpath.basename(f) for f in shipped}
    code = {p: c for p, c in files.items() if p.endswith((".qml", ".js", ".mjs", ".sh", ".py", ".bash")) and
            not re.search(r"(^|/)(tests?|spec|scripts/(lint|live_smoke|check)\w*|install)[_./-]|_test\.|\.test\.|\.spec\.", p)}
    io_re = r"\b(Process|execDetached|FileView|XMLHttpRequest|Socket|IpcHandler|SplitParser|StdioCollector|Mpris|Pipewire|UPower|SystemTray|Hyprland\.|NotificationServer|Bluetooth|Networking|DesktopEntries|Qt\.openUrlExternally|subprocess|urllib|requests\.|curl|ToplevelManager|SystemClock|Date\(|PwObjectTracker)\b"
    plugin_io = any(re.search(io_re, c) for c in code.values())

    # ---- commands (argv arrays, sh -c strings, shipped shell scripts)
    cmds = []   # (file, offset, argv0, args, via)
    for p, c in code.items():
        lang = "py" if p.endswith(".py") else ("sh" if p.endswith((".sh", ".bash")) else "qml")
        shebang = c.split("\n", 1)[0]
        if shebang.startswith("#!") and lang == "sh" and not re.search(r"\b(ba|da|z)?sh\b", shebang): lang = "py" if "python" in shebang else "other"
        if lang == "other": continue
        if lang == "sh":
            body = re.sub(r"(^|\s)#[^\n!]*", r"\1", c)
            body = re.sub(r"<<-?\s*['\"]?(\w+)['\"]?.*?^\s*\1$", "", body, flags=re.S | re.M)
            body = re.sub(r"\b(python3?|perl|ruby|node|awk|gawk|jq|sed|lua|luajit)\b((?:\s+-{1,2}[\w-]+)*)\s+(['\"])(?:\\.|(?!\3).)*\3", r"\1", body, flags=re.S)
            g = guarded_words(body); alt = any(a in body for a in WAYLAND_ALT)
            for w, rest in shell_words(body):
                if w in g and (alt or w not in X11_TOOLS): continue
                cmds.append((p, 0, w, rest, "script"))
            continue
        for off, argv in argv_arrays(c, lang):
            if not argv or argv[0] is None: continue
            a0 = os.path.basename(argv[0]) if argv[0].startswith("/usr/") or argv[0].startswith("/bin/") else argv[0]
            if a0 in ("sh", "bash", "dash", "zsh") and len(argv) >= 3 and argv[1] in ("-c", "-lc", "-ec", "-euc"):
                if argv[2] is None: continue
                g = guarded_words(argv[2]); alt = any(a in argv[2] for a in WAYLAND_ALT)
                for w, rest in shell_words(argv[2]):
                    if w in g and (alt or w not in X11_TOOLS): continue
                    cmds.append((p, off, w, rest, f"{a0} -c"))
            else:
                cmds.append((p, off, a0, [x if x is not None else "<expr>" for x in argv[1:]], "argv"))
        # any other array literal that starts with a known binary (e.g. `cond ? ["hyprsunset", "enable"] : [...]`)
        for m in re.finditer(r"\[\s*([\"'])(hyprctl|hyprsunset|%s)\1\s*(,[^\[\]\n]*)?\]" % "|".join(X11_TOOLS), c):
            rest = [x[1] for x in re.findall(r"([\"'])((?:(?!\1).)*)\1", m.group(3) or "")]
            if not any(o == m.start() or abs(o - m.start()) < 40 for (pp, o, *_r) in cmds if pp == p):
                cmds.append((p, m.start(), m.group(2), rest, "argv"))
        if lang == "py":
            for m in re.finditer(r"\bos\.system\(\s*(['\"])(.*?)\1|shell=True", c):
                if m.group(2):
                    for w, rest in shell_words(m.group(2)): cmds.append((p, m.start(), w, rest, "os.system"))
    docs = " ".join(files.get(f, "") for f in ("README.md", "README", "readme.md")) + json.dumps(man)
    seen = set()
    for p, off, w, rest, via in cmds:
        base = posixpath.basename(w)
        if base in X11_TOOLS:
            k = ("x11", p, base)
            if k not in seen:
                seen.add(k); add("USB-B02", "error", p, f"runs `{base}` ({via}), an X11-only tool; Omarchy is a Wayland/Hyprland session, so it does nothing (or is not installed on the Dell)", X11_TOOLS[base])
            continue
        if via != "argv" and via != "script" or via == "script":
            # binaries inside sh -c strings / scripts / os.system; argv[0] of plain arrays is dell_checks' exec-unknown-binary
            if "/" in w and not w.startswith("/"):
                if w.lstrip("./") not in shipped and base not in shipped_base:
                    k = ("helper", p, w)
                    if k not in seen: seen.add(k); add("USB-F01", "error", p, f"{via} runs helper `{w}`, which the plugin does not ship", f"add `{w}` to the plugin (and reference it via the plugin directory), or inline the logic")
                continue
            if w.startswith("/") or base in shipped_base or w in SH_WORDS: continue
            if not resolves(w, shipped) and w not in docs:
                k = ("bin", p, w)
                if k not in seen:
                    seen.add(k); add("USB-B01", "error", p, f"{via} string runs `{w}`, which is not installed on the Dell's Omarchy 4.0.4 (system_bins) and not shipped by the plugin", f"use a binary that exists on stock Omarchy (see dell_env/system_bins.txt), ship a script for it, or document `{w}` as a dependency in README.md")
        # hyprctl / hyprsunset subcommands
        if base == "hyprctl":
            r = [x for x in rest if x != "<expr>"]
            i = 0
            while i < len(r) and r[i].startswith("-"):
                if r[i].startswith("--batch"): i = len(r); break
                i += 2 if r[i] in ("-i", "--instance") else 1
            if i < len(r):
                sub = r[i].strip("\"'")
                if re.match(r"^[a-z]+$", sub) and sub not in HYPRCTL_SUB:
                    add("USB-B03", "error", p, f"`hyprctl {sub}` is not a hyprctl command", "valid commands include dispatch, keyword, getoption, monitors, clients, activewindow, hyprpaper, hyprsunset; wallpapers go through `swaybg`/`hyprpaper` or Omarchy's `omarchy-theme-bg-*` scripts")
                elif sub == "hyprsunset" and i + 1 < len(r) and re.match(r"^[a-z]+$", r[i + 1]) and r[i + 1] not in HYPRSUNSET_IPC:
                    add("USB-B03", "error", p, f"`hyprctl hyprsunset {r[i+1]}` is not a hyprsunset IPC command", "use `hyprctl hyprsunset temperature <K>` / `identity` / `gamma <n>`")
        if base == "hyprsunset":
            r = [x for x in rest if x != "<expr>"]
            if r and re.match(r"^[a-z]+$", r[0]):
                add("USB-B03", "error", p, f"`hyprsunset {r[0]}` is not valid: hyprsunset takes flags only (-t/--temperature, -g/--gamma, -i/--identity)", "start it with `hyprsunset -t 4500`, change it live with `hyprctl hyprsunset temperature 4500`, turn it off with `hyprctl hyprsunset identity` or `pkill hyprsunset`")
    # hyprctl keyword ... then hyprctl reload in the same file: the reload discards the runtime keywords
    for p, c in code.items():
        ws = [(w, rest) for (pp, _, w, rest, _) in cmds if pp == p and posixpath.basename(w) == "hyprctl"]
        subs = [next((x for x in r if not x.startswith("-")), "") for _, r in ws]
        if p.endswith(".py"):
            subs += re.findall(r"\[\s*\w*HYPR\w*\s*,\s*['\"](\w+)['\"]", c, re.I)
        if "keyword" in subs and "reload" in subs:
            add("USB-B04", "error", p, "sets options with `hyprctl keyword` and also runs `hyprctl reload`, which re-reads hyprland.conf and discards those runtime keywords", "drop the `hyprctl reload`; keywords apply immediately (or batch them with `hyprctl --batch`)")

    # ---- helper scripts referenced from QML/JS but not shipped
    for p, c in code.items():
        if not p.endswith((".qml", ".js")): continue
        cf = _cks(c)
        for off, lit in [(m.start(), m.group(2)) for m in re.finditer(r"(['\"`])((?:\\.|(?!\1)[^\n])*?)\1", cf)]:
            ctxt = cf[max(0, off - 160):off]
            if not re.search(r"(command\s*[:=]|exec\w*\s*\(|resolvedUrl\s*\(|\[\s*(['\"])(?:ba)?sh\2|\b(?:pluginDir|pluginPath|scriptDir|scriptsDir|binDir|shellDir|dir|path|Path|Dir)\s*\+\s*$|\+\s*$)", ctxt) and not lit.startswith(("./", "bin/", "scripts/")): continue
            for m in re.finditer(r"(?:^|[\s/\"'])((?:\.{0,2}/)?(?:[\w.-]+/)*[\w.-]+\.(?:sh|py|rb|pl|bash))(?=$|[\s\"'])", lit):
                ref = m.group(1)
                if ref.startswith(("/usr", "/bin", "/etc", "/opt")) or "omarchy/bin" in lit: continue
                b = posixpath.basename(ref)
                if b not in shipped_base and not resolves(b, shipped):
                    k = ("helper", p, b)
                    if k not in seen: seen.add(k); add("USB-F01", "error", p, f"references helper script `{ref}`, which the plugin does not ship", f"ship `{ref}` in the plugin (e.g. bin/{b}) or inline the command")

    # ---- QML: types, handlers, calls, invented APIs
    qml = {p: c for p, c in code.items() if p.endswith((".qml", ".js"))}
    for p, c in qml.items():
        san = sanitize(c)
        for pat, what, hint in INVENTED:
            for m in re.finditer(pat, san):
                add("USB-A01", "error", p, f"line {lineno(c, m.start())}: {what}", hint); break
        # `new X(` of a QML type
        for m in re.finditer(r"\bnew\s+([A-Z]\w*)\s*\(", san):
            t = m.group(1)
            if t in JS_NEW_OK or "Animation" in t and re.search(INVENTED[3][0], san): continue
            if t in ALL_TYPE_HOMES:
                add("USB-A03", "error", p, f"line {lineno(c, m.start())}: `new {t}()` - QML types cannot be instantiated with JavaScript `new`", f"declare `{t} {{ id: ... }}` in QML, or use `Qt.createQmlObject` / a `Component` + `createObject()`")
        if not p.endswith(".qml"): continue
        env, aliases, open_world = file_env(p, c, files)
        objs = qml_objects(san)
        ids = {}
        for o in objs:
            body = san[o["lb"]:o["rb"]]
            im = None
            for off, ln in direct_children(san, o["lb"], o["rb"]):
                mm = re.match(r"\s*id\s*:\s*(\w+)", ln)
                if mm: im = mm.group(1); break
            if im is None:
                mm = re.match(r"\{\s*id\s*:\s*(\w+)", san[o["lb"]:o["lb"] + 80])
                im = mm.group(1) if mm else None
            o["id"] = im
            tdef = resolve(o["type"], env, aliases)
            if tdef is None and not open_world:
                homes = [h for h in ALL_TYPE_HOMES.get(o["type"].split(".")[-1], []) if not h.startswith(("QtQuick.Controls.", "QtQuick.Templates")) or True]
                local = [f for f in files if posixpath.basename(f) == o["type"] + ".qml"]
                if local: hint = f"{local[0]} exists but is not in this file's directory; add `import \"{posixpath.relpath(posixpath.dirname(local[0]) or '.', posixpath.dirname(p) or '.')}\"`"
                elif homes: hint = f"add `import {sorted(homes, key=len)[0]}`" + (" (Qt6 GraphicalEffects need Qt5Compat.GraphicalEffects or QtQuick.Effects MultiEffect)" if o["type"] == "DropShadow" else "")
                else: hint = "no Qt 6, Quickshell or Omarchy module provides this type; use a real type or ship it as a QML file"
                add("USB-Q01", "error", p, f"line {lineno(c, o['start'])}: unknown QML type `{o['type']}` - not provided by any module this file imports", hint)
                continue
            if isinstance(tdef, dict) and tdef.get("inline"): continue
            o["tdef"] = tdef
            if tdef is None: continue
            sig, props, meth, complete = members_of(tdef, env)
            if not complete: continue
            own = set(re.findall(r"\b(?:property\s+[\w.<>]+|signal|alias|function)\s+(\w+)", body))
            meth = meth | own
            sig |= own; props |= own
            if o["id"]: ids[o["id"]] = (o["type"], sig, props, meth)
            for off, ln in direct_children(san, o["lb"], o["rb"]):
                for mm in re.finditer(r"(?:^|;|\{)\s*(on([A-Z]\w*))\s*:", ln):
                    h, nm = mm.group(1), mm.group(2)
                    base = nm[0].lower() + nm[1:]
                    ok = base in sig or (base.endswith("Changed") and base[:-7] in props) or nm in sig or (nm.endswith("Changed") and nm[:-7] in props)
                    ok = ok or (base.endswith("Changed") and (nm[:-7] in props or base[:-7] in sig))
                    if not ok:
                        real = sorted(s for s in sig if not s.endswith("Changed"))[:8]
                        add("USB-A02", "error", p, f"line {lineno(c, off)}: `{h}` is not a signal of `{o['type']}` (handler never fires)",
                            f"`{o['type']}` signals: {', '.join(real) or 'none besides <prop>Changed'}" + ("; for Process use `onExited: (code) => ...` and `stdout: StdioCollector { onStreamFinished: ... }`" if o["type"] == "Process" else ""))
        # method calls on ids of fully-known types
        QOBJ = {"destroy", "toString", "hasOwnProperty", "forceActiveFocus", "objectName", "connect", "disconnect"}
        for m in re.finditer(r"(?<![\w.])(\w+)\.([a-z]\w*)\s*\(", san):
            i, meth_name = m.group(1), m.group(2)
            if i in ids and not re.search(r"\b(?:var|let|const|property\s+[\w.<>]+)\s+" + i + r"\b|[(,]\s*" + i + r"\s*[,)]", san):
                t, sig, props, meth = ids[i]
                if meth_name not in meth and meth_name not in sig and meth_name not in props and meth_name not in QOBJ and not meth_name.endswith("Changed"):
                    hint = "set `running = true` to start a Process (there is no start())" if t == "Process" and meth_name in ("start", "run", "execute", "exec") else f"real `{t}` methods: {', '.join(sorted(x for x in meth if not x.startswith('on'))[:10])}"
                    add("USB-A04", "error", p, f"line {lineno(c, m.start())}: `{i}.{meth_name}()` - `{t}` has no method `{meth_name}`", hint)
        # Capitalised roots: Qt.*, Quickshell.*, singletons, type static calls
        for m in re.finditer(r"(?<![\w.])([A-Z]\w*)\.([a-z_]\w*)\b(\s*\()?", san):
            root, mem, call = m.group(1), m.group(2), m.group(3)
            if root == "Qt":
                if mem not in QT_GLOBAL: add("USB-A01", "error", p, f"line {lineno(c, m.start())}: `Qt.{mem}` does not exist on the Qt global object", "see https://doc.qt.io/qt-6/qml-qtqml-qt.html for the real members")
                continue
            if root == "Quickshell" and "Quickshell" in env:
                if mem not in qs_members(): add("USB-A01", "error", p, f"line {lineno(c, m.start())}: `Quickshell.{mem}` is not a member of the Quickshell singleton", "real members include execDetached, env, shellDir, dataDir, stateDir, screens, iconPath, reload")
                continue
            if root in JS_GLOBALS or root in ids or root in aliases or not call: continue
            tdef = resolve(root, env, aliases)
            if tdef is None:
                if open_world or re.search(r"\b(property\s+[\w.<>]+|id\s*:|var|let|const|function)\s+" + root + r"\b|\bid\s*:\s*" + root + r"\b", san): continue
                add("USB-A01", "error", p, f"line {lineno(c, m.start())}: `{root}.{mem}()` calls an undefined object `{root}` (ReferenceError at runtime)", "use a real API: an id in scope, a qs.Commons singleton, `Quickshell.execDetached`, or omarchy-shell IPC")
            else:
                singleton = (isinstance(tdef, str) and COMPS.get(tdef, {}).get("singleton")) or (isinstance(tdef, dict) and tdef.get("singleton"))
                if isinstance(tdef, dict) and tdef.get("local"):
                    singleton = bool(re.search(r"^\s*pragma\s+Singleton", files.get(tdef["local"], ""), re.M))
                if not singleton and not (isinstance(tdef, str) and COMPS.get(tdef, {}).get("attached")):
                    add("USB-A01", "error", p, f"line {lineno(c, m.start())}: `{root}.{mem}()` calls a method on the type `{root}`, not on an instance (it is not a singleton)", f"give the `{root}` object an id (or receive it as a property) and call the method on that")
        # undeclared roots that are assigned or dereferenced (swallowed ReferenceErrors)
        declared = set(re.findall(r"\b(?:property\s+[\w.<>]+|signal|alias|function|var|let|const|id\s*:)\s*(\w+)", san))
        declared |= set(re.findall(r"\bfunction\s*\w*\s*\(([^)]*)\)", san) and sum((re.findall(r"\w+", x) for x in re.findall(r"\bfunction\s*\w*\s*\(([^)]*)\)", san)), []))
        declared |= set(sum((re.findall(r"\w+", x) for x in re.findall(r"\(([^()]*)\)\s*=>", san)), [])) | set(re.findall(r"\b(\w+)\s*=>", san))
        declared |= set(re.findall(r"\bcatch\s*\(\s*(\w+)", san)) | set(re.findall(r"\bfor\s*\(\s*(?:var|let|const)?\s*(\w+)\s+(?:in|of)\b", san))
        declared |= set(re.findall(r"\b(?:var|let|const)\s*[\[{]([^\]}=]*)[\]}]", san) and sum((re.findall(r"\w+", x) for x in re.findall(r"\b(?:var|let|const)\s*[\[{]([^\]}=]*)[\]}]", san)), []))
        for st in re.findall(r"\b(?:var|let|const)\s+([^;\n]*)", san):
            declared |= set(re.findall(r"(?:^|,)\s*([A-Za-z_$][\w$]*)", re.sub(r"\[[^\]]*\]|\{[^}]*\}|\([^)]*\)", "", st)))
        ctx = {"parent", "model", "modelData", "index", "mouse", "event", "wheel", "drag", "root", "this", "arguments", "window", "screen", "data", "text", "value", "checked", "point", "eventPoint", "status", "exitCode", "exitStatus", "line", "delta", "args", "pluginApi", "panel", "bar", "settings", "service", "shellRoot", "modelIndex", "action", "reason", "error"}
        allprops = set()
        for o in objs:
            td = o.get("tdef")
            if td is not None:
                s_, p_, m_, _ = members_of(td, env); allprops |= s_ | p_ | m_
        js_blocks = [(m.end(), match_brace(san, m.end() - 1)) for m in re.finditer(r"(?:\bfunction\b[^{]*|\bon[A-Z]\w*\s*:\s*(?:\([^)]*\)\s*=>\s*)?)\{", san)]
        for a, b in js_blocks:
            blk = san[a:b]
            for m in re.finditer(r"(?:^|[;{(!&|?:,=\s])\s*([a-z_]\w*)\s*(?:\.\w|(?<![=!<>])=(?!=))", blk, re.M):
                nm = m.group(1)
                if nm in declared or nm in ctx or nm in allprops or nm in JS_GLOBALS or nm in ("return", "typeof", "new", "delete", "void", "in", "of", "if", "else", "case", "throw", "await", "yield", "instanceof", "do", "true", "false", "null", "undefined") or open_world: continue
                if re.search(r"\b" + nm + r"\b", " ".join(json.dumps(x) for x in [list(env)[:0]])): continue
                pos = a + m.start(1)
                in_try = re.search(r"\btry\s*\{", san[max(0, pos - 2000):pos]) is not None
                add("USB-J01", "error", p, f"line {lineno(c, pos)}: `{nm}` is never declared (no property, id, var or parameter) - ReferenceError at runtime" + (", silently swallowed by try/catch so the feature just shows nothing" if in_try else ""),
                    f"declare `property var {nm}` (and fill it), or use a real API object; never hide missing APIs behind try/catch")
                declared.add(nm)

    # ---- heuristics (severity graded): fake/simulated/placeholder data, console.log-only handlers, demo handlers
    for p, c in qml.items():
        if not p.endswith(".qml"): continue
        cm = " ".join(re.findall(r"//[^\n]*|/\*.*?\*/", c, re.S))
        m = re.search(r"(?i)\b(simulat\w* (?:data|values?|readings?|results?|output|response|api)|safe simulation|simulation only|mock(?:ed)? data|fake data|dummy data|sample data|placeholder (?:data|value)s?|hard-?coded (?:data|value)s?|in production,? replace|for (?:the )?demo)\b", cm + " " + " ".join(l for _, l in str_lits(c)))
        if m:
            explicit = re.search(r"(?i)simulat|mock|fake|dummy|in production", m.group(1))
            sev = "high" if (explicit or not plugin_io) else "medium"
            add("USB-H01", sev, p, f"says its data is `{m.group(1)}`" + ("" if plugin_io else " and the plugin reads no real data source (no Process/FileView/service/IO)"), "read the real source (Process + StdioCollector, FileView, a Quickshell service) instead of shipping canned values")
        for mm in re.finditer(r"\btext\s*:\s*([\"'])([^\"'\n]*\d+(?:\.\d+)?\s*(?:°\s?[CF]?|%|GB|MB|KB|Mbps|MB/s|km/h|mph|hPa|W)\b[^\"'\n]*)\1\s*$", c, re.M):
            sev = "medium" if plugin_io else "high"
            add("USB-H02", sev, p, f"line {lineno(c, mm.start())}: hardcoded reading `{mm.group(2)}` shown as live data", "bind the text to a property filled from a real data source")
            break
    allq = "\n".join(sanitize(c) if False else c for p, c in qml.items() if p.endswith(".qml"))
    logs = len(re.findall(r"\bconsole\.(log|debug|info)\(", allq))
    if qml and not plugin_io and logs >= 3:
        add("USB-H03", "high", "*", f"{logs} console.log calls and no real side effect anywhere (no Process, exec, FileView, IPC or service): handlers only log", "make each handler do the real action (Process / Quickshell.execDetached / omarchy-shell IPC / settings write)")
    elif qml and logs >= 6:
        add("USB-H03", "low", "*", f"{logs} console.log calls", "remove debug logging before shipping")
    for p, c in qml.items():
        for mm in re.finditer(r"\bon(Clicked|Pressed|Tapped|Triggered)\s*:\s*\{([^{}]*)\}", c):
            blk = mm.group(2)
            acts = [l.strip() for l in blk.splitlines() if l.strip()]
            if acts and all(re.search(r"console\.\w+\(|notify-send|var\s+cmd\s*=|execDetached\(cmd\)", l) for l in acts) and re.search(r"(?i)click|press|tap", blk):
                add("USB-H04", "high", p, f"line {lineno(c, mm.start())}: on{mm.group(1)} only reports that it was clicked (debug/demo handler, no real action)", "make the click do what the plugin is for")
    out, seen2 = [], set()
    for f in finds:
        k = (f["rule"], f["file"], f["reason"])
        if k not in seen2: seen2.add(k); out.append(f)
    return out

def blocking(f): return f["severity"] in ("error", "high")
def fmt(f):
    tag = f["rule"] + ("" if f["severity"] == "error" else f" heuristic/{f['severity']}")
    return f"[{tag}] {f['file']}: {f['reason']}. Fix: {f['hint']}"

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(HERE)); import functest
    for f in check(functest.read_dir(sys.argv[1])): print(("FAIL " if blocking(f) else "warn ") + fmt(f))
