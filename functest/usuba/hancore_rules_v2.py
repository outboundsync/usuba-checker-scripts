#!/usr/bin/env python3
"""USB-HC rules (renamed from USB-H01..H25 in v3-fixes to end the clash with rules.py USB-H01..H07): finer-grained static rules for the HANCORE security categories (v2). Advisory only (never fails a plugin).
Each finding is dict(rule, category, file, line, reason, hint, severity). Every finding carries file AND line (>=1).
Derived from the text of HANCORE findings on the design split only (see docs/TRAINING_PLAN.md 'Checker rules v2');
measured by hancore/measure_rules_v2.py. RULES[rule] = (category, one-line summary). ENABLED = rules that met the keep bar.
check(files, enabled=None, per_file=3) -> list of findings. CLI: python3 hancore_rules_v2.py PLUGIN_DIR"""
import re, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from hancore_rules import _lines, SECRET_PATS, PLACEHOLDER, SKIP_PATH
CODE_EXT = (".qml", ".js", ".mjs", ".sh", ".bash", ".zsh", ".py", ".lua")
SHELLY = (".sh", ".bash", ".zsh")
def _is_shell_file(p, c):
    return p.endswith(SHELLY) or (not os.path.splitext(p)[1] and c.startswith("#!") and re.match(r"#!.*\b(ba|z)?sh\b", c.split("\n", 1)[0]) is not None)
def _is_py(p, c): return p.endswith(".py") or (not os.path.splitext(p)[1] and c.startswith("#!") and "python" in c.split("\n", 1)[0])
RULES = {
 "USB-HC01": ("unbounded-input-resource", "curl/wget download with no byte cap (--max-filesize / head -c)"),
 "USB-HC02": ("unbounded-input-resource", "Python network/socket body read with no size limit"),
 "USB-HC03": ("unbounded-input-resource", "QML XMLHttpRequest response parsed without a length check"),
 "USB-HC04": ("file-safety-symlink-perms", "predictable fixed /tmp (or tmp.$$) path"),
 "USB-HC05": ("file-safety-symlink-perms", "world-writable mode / umask 0 / mkdir -m 777"),
 "USB-HC06": ("file-safety-symlink-perms", "forced symlink, or rm -rf on an unvalidated variable"),
 "USB-HC07": ("file-safety-symlink-perms", "secret-bearing file written without a 0600/umask 077"),
 "USB-HC08": ("secrets-credentials", "hardcoded credential literal"),
 "USB-HC09": ("secrets-credentials", "secret passed in argv / URL query"),
 "USB-HC10": ("url-scheme-network", "plain http:// remote endpoint or TLS verification disabled"),
 "USB-HC11": ("url-scheme-network", "Qt.openUrlExternally / xdg-open of a non-literal URL"),
 "USB-HC12": ("url-scheme-network", "redirect following with credentials or without --proto"),
 "USB-HC13": ("rich-text-markup-injection", "QML Text with dynamic text and default AutoText / explicit rich format"),
 "USB-HC14": ("shell-lua-injection", "value interpolated into sh -c / eval / hyprctl dispatch / Lua string"),
 "USB-HC15": ("privileged-system", "sudo/pkexec/system-level write or device/capability access"),
 "USB-HC16": ("privileged-system", "coding-agent control file (AGENTS.md/CLAUDE.md/...) shipped in the plugin"),
 "USB-HC17": ("remote-code-pinning", "remote code fetched/installed without an immutable pin"),
 "USB-HC18": ("process-lifecycle-timeouts", "network/subprocess call without a timeout"),
}
def _model_specs():
    import json
    f = os.path.join(HERE, "model_rules_v3.json")
    with open(f) as fh: return json.load(fh)["rules"]   # a missing config file is an error, not "no rules" (audit D3)
MODEL_SPECS = _model_specs()   # USB-HC19+: data-only specs proposed by qwen/qwen3.5-397b-a17b, kept on design (see model_rules_v3.json)
for _k, _s in MODEL_SPECS.items(): RULES[_k] = (_s["category"], _s["summary"])
_COMPILED = {}
def _compiled_model_specs(en):
    """Compile (and timing-validate) the model-proposed specs ONCE per process, not inside every check() (audit D3)."""
    import hancore_rules_model as MR
    for k in sorted(k for k in MODEL_SPECS if k in en and k not in _COMPILED):
        _COMPILED[k] = dict(MR.compile_spec(MODEL_SPECS[k]), summary=MODEL_SPECS[k]["summary"])
    return {k: v for k, v in _COMPILED.items() if k in en}
def load_enabled():
    import json
    f = os.path.join(HERE, "rules_v2_enabled.json")
    with open(f) as fh: d = json.load(fh)   # missing enabled-list = error; previously every rule silently became enabled (audit D3)
    en = set(d.get("enabled_v3_fixes", d.get("enabled_v3", d["enabled"])))
    unknown = en - set(RULES)
    if unknown: raise ValueError("rules_v2_enabled.json names unknown rules: %s" % sorted(unknown))
    return en
ENABLED = load_enabled()
def hardware_status():
    """Hit-check evidence per rule (results/hitcheck): which rules were observed breaking a plugin on real hardware, which are static advisories only."""
    import json
    f = os.path.join(HERE, "rule_hardware_status.json")
    with open(f) as fh: return json.load(fh)["rules"]
HARDWARE_STATUS = hardware_status()
EXPERIMENTAL = set(RULES) - ENABLED   # measured below the keep bar; pass enabled=set(RULES) to run them

VENDOR_DIR = re.compile(r"(^|/)(vendor|vendored|third[_-]?party|upstream|external|extern|deps)(/|$)", re.I)
LICENSE_NAMES = ("license", "license.md", "license.txt", "copying", "copying.md", "licence")
def vendored_prefixes(files):
    """v3-fixes (winners follow-up): subtrees that are not the plugin's own code: vendor-like dir names, non-root dirs that carry their own LICENSE/COPYING
    (and no manifest.json), and dirs named in UPSTREAM.md / VENDORED.md / THIRD_PARTY*.md / NOTICE*. Rules skip files under these prefixes."""
    out = set(); dirs = {}
    for p in files:
        d, _, b = p.rpartition("/")
        if d and b.lower() in LICENSE_NAMES: dirs[d] = True
    for d in dirs:
        if (d + "/manifest.json") not in files: out.add(d + "/")
    for p, c in files.items():
        b = p.rsplit("/", 1)[-1].lower()
        if b.startswith(("upstream", "vendored", "third_party", "third-party", "thirdparty", "notice")):
            for m in re.finditer(r"`?((?:[\w.-]+/)+)`?", c):
                d = m.group(1)
                if any(q.startswith(d) for q in files) and not d.startswith(("docs/", "http")) and len(d) > 2: out.add(d)
    return out
def is_vendored(p, pref): return bool(VENDOR_DIR.search(p)) or any(p.startswith(x) for x in pref)
def _guarded(var, c):
    """variable validated by a regex/case guard somewhere in the script ([[ $v =~ ^...$ ]], case $v in)"""
    v = re.escape(var)
    return bool(re.search(r"\[\[\s*\"?\$\{?" + v + r"\}?\"?\s*=~\s*\^|case\s+\"?\$\{?" + v + r"\}?\"?\s+in", c))
def _mktemp_var(var, c):
    v = re.escape(var); return bool(re.search(r"\b" + v + r"=[\"']?\$\(\s*mktemp\b|\b" + v + r"=[\"']?`\s*mktemp\b", c))
def _cont(L, i, t):
    """statement text extended over shell backslash continuations (so a trailing `>/dev/null 2>&1` on a later line is seen)"""
    j = i
    while j < len(L) and L[j][1].rstrip().endswith("\\") and j + 1 < len(L) and j - i < 12:
        j += 1; t += " " + L[j][1].strip()
    return t
def _rm_var_safe(txt, c):
    v = re.search(r"\$\{?([A-Za-z_]\w*)", txt)
    return bool(v) and "rm" in txt and (_mktemp_var(v.group(1), c) or _guarded(v.group(1), c))
def _win(L, i, n=6):
    """statement text starting at L[i]: this line + up to n following lines while a bracket is open."""
    t = L[i][1]; depth = t.count("[") + t.count("(") - t.count("]") - t.count(")"); j = i
    while depth > 0 and j + 1 < len(L) and j - i < n:
        j += 1; t += " " + L[j][1].strip(); depth += L[j][1].count("[") + L[j][1].count("(") - L[j][1].count("]") - L[j][1].count(")")
    return t
CURL = re.compile(r"(?<![\w./-])(curl|wget)(?![\w-])")
NOT_RUN = re.compile(r"\b(command\s+-v|which|type\s+-p|hash|have|need|require|need_cmd|check_cmd|has_cmd|install|pacman|yay|paru|apt|dnf)\b[^\n]{0,20}\b(curl|wget)\b|\"(curl|wget)\"\s*\]?\s*\)?\s*(\.|;|,)?\s*$|echo\b|printf\b|\bnotify-send\b|\bError|\bmissing", re.I)
SECRET_NAME = r"(?:token|api_?key|apikey|secret|passw(?:or)?d|passwd|bearer|credential|auth_?key|access_?key|private_?key|client_?secret)"
LOCAL_HOST = r"(?:localhost|127\.|0\.0\.0\.0|\[::1\]|192\.168\.|10\.\d|172\.(?:1[6-9]|2\d|3[01])\.|[\w.-]*\.local\b|[\w.-]*\.lan\b|\$|\{|%s|%d)"
NS_URL = r"(?:www\.w3\.org|schemas?\.|purl\.org|xmlns|json-schema\.org|ns\.adobe|www\.freedesktop\.org|specifications\.freedesktop|creativecommons|example\.(?:com|org)|gnu\.org/licenses|www\.apache\.org/licenses|opensource\.org|spdx\.org|www\.gnu\.org|xmlsoft|relaxng|www\.iana\.org)"

TEXT_TYPES = r"(?:Text|Label|StyledText|NText|ToolTip|ShadowedText|StyledLabel|NLabel|ElidedText)"
def _blocks(c):
    """yield (start_offset, type, body) for Text-like QML objects, brace matched (best effort, nested objects included in body)."""
    for m in re.finditer(r"(?m)^[ \t]*(?:[\w.]+\s*:\s*)?(" + TEXT_TYPES + r")\s*\{", c):
        i = m.end(); d = 1
        while i < len(c) and d:
            ch = c[i]
            if ch == "{": d += 1
            elif ch == "}": d -= 1
            elif ch in "\"'":
                q = ch; i += 1
                while i < len(c) and c[i] != q and c[i] != "\n":
                    i += 2 if c[i] == "\\" else 1
            i += 1
        yield m.start(1), m.group(1), c[m.end():i - 1]
def _own_lines(body):
    """[(line_index_in_body, text)] of top-level (depth 0) lines, so child objects' properties are not attributed to the parent."""
    d = 0; out = []
    for i, ln in enumerate(body.split("\n")):
        if d == 0: out.append((i, ln))
        d += ln.count("{") - ln.count("}")
        if d < 0: d = 0
    return out
LITERAL_TEXT = re.compile(r"^\s*(?:qsTr\(|qsTrId\(|qsTranslate\(|i18n\(|\"[^\"\\]*\"\s*$|'[^'\\]*'\s*$|[\d.]+\s*$|Qt\.formatDate|Qt\.locale|Math\.|String\(Math|Number\()")
DATA_ID = re.compile(r"\b(modelData|stdout|stderr|response|reply|payload|ssid|artist|album|summary|body|alias|deviceName|trackTitle|appName|windowTitle|description|message|snippet|headline|excerpt|subtitle)\b|\bmodel\.\w+|\.(?:title|name|desc\w*|label|content|text|summary|display\w*)\b", re.I)
EXT_SRC = re.compile(r"\b(StdioCollector|SplitParser|XMLHttpRequest|Mpris|NotificationServer|Notification\b|Bluetooth|Networking|FileView|DesktopEntries|Hyprland\.|HyprlandWindow|SystemTray|ToplevelManager|\.stdout|Process\s*\{|JSON\.parse)")

def check(files, enabled=None, per_file=3):
    en = ENABLED if enabled is None else enabled
    out = []; cnt = {}
    def add(rule, f, line, reason, hint="", sev="medium"):
        if rule not in en: return
        k = (rule, f)
        if cnt.get(k, 0) >= per_file: return
        cnt[k] = cnt.get(k, 0) + 1
        out.append(dict(rule=rule, category=RULES[rule][0], file=f, line=max(1, line), reason=reason, hint=hint, severity=sev))
    vend = vendored_prefixes(files)
    code = {p: c for p, c in files.items() if (p.endswith(CODE_EXT) or (not os.path.splitext(p)[1] and c.startswith("#!"))) and not SKIP_PATH.search(p) and len(c) < 400_000 and not is_vendored(p, vend)}
    # H16 agent control files (published plugin tree)
    for p in files:
        b = p.lower()
        if b in ("agents.md", "claude.md", "gemini.md", ".cursorrules", "copilot-instructions.md", ".github/copilot-instructions.md", "agent.md", "codex.md", "cursorrules") or b.startswith((".cursor/rules", ".claude/")):
            add("USB-HC16", p, 1, f"`{p}` ships coding-agent instructions inside the installable plugin tree", "remove agent-control files from the published plugin (or exclude them from the package)")
    qml_all = "\n".join(c for p, c in code.items() if p.endswith((".qml", ".js")))
    for p, c in code.items():
        isqml = p.endswith((".qml", ".js", ".mjs")); sh = _is_shell_file(p, c); py = _is_py(p, c); lua = p.endswith(".lua")
        L = [(n, ln) for n, ln in _lines(c, p)] if not (sh or py) else [(n, ln) for n, ln in _lines(c, p)]
        has_chmod600 = re.search(r"chmod\s+(?:-\w+\s+)?0?[67]00\b|umask\s+0?(?:07|077)\b|0o?[67]00\b|\bumask\(0o?077\)|install\s+[^\n]*-m\s*0?[67]00|mkdir\s+-m\s*0?700|mode\s*[:=]\s*0o?[67]00|O_CREAT[^\n]*0o?[67]00|NoFollow|O_NOFOLLOW", c)
        has_cap = re.search(r"--max-filesize|head\s+-c|head\s+-n|\bMAX_\w+|max_?(bytes|size|len)\w*|\bLIMIT\w*|\.read\(\s*\w+\s*\)|\bmaxLength\b|--limit-rate|\bquota\b|Content-Length|\bhead\b\s+-\d", c, re.I)
        has_timeout_any = re.search(r"\btimeout\s+\d|\btimeout\b\s+-", c)
        pinned = re.search(r"(?m)^\s*git\s+(-C\s+\S+\s+)?(checkout|reset --hard)\s+[0-9a-f]{7,40}\b|sha256sum|sha512sum|shasum|gpg\s+--verify|cosign\s+verify|minisign|--checksum|--hash", c)
        for i, (n, ln) in enumerate(L):
            st = None
            def S():
                nonlocal st
                if st is None: st = _win(L, i)
                return st
            # ---------- H01 curl/wget unbounded
            if (sh or isqml or py) and CURL.search(ln) and not NOT_RUN.search(ln) and re.search(r"https?://|\$\{?\w*(url|URL|endpoint|feed|api)\w*|\burl\b|-o\b|-O\b|-s|-f|-L|--", ln) and not re.search(r"[|]\s*head\s+-c|--max-filesize|--limit-rate|--quota", S()) and not re.search(r"(?:^|\s)(?:-o|--output)[ =]*[\"']?/dev/null\b|>\s*/dev/null", _cont(L, i, S())):
                if not (py and "subprocess" not in ln and "[" not in ln):
                    add("USB-HC01", p, n, "curl/wget response is not size-limited (--max-time is a time limit, not a byte cap); a hostile or compromised endpoint can stream unbounded data into memory/disk", "add --max-filesize N (and head -c N / a producer-side cap) and reject overflow")
            # ---------- H18 curl without timeout
            if (sh or isqml or py) and CURL.search(ln) and not NOT_RUN.search(ln) and re.search(r"https?://|\$\{?\w*(url|URL|endpoint|feed|api)\w*|\burl\b|-sS?f?L?\b|-s\b", ln) and not re.search(r"--max-time|--connect-timeout|\s-m\s*\d|\s-m\s*\$|--timeout|\btimeout\s+\d|-T\s*\d|--speed-limit", S()) and not has_timeout_any and not (re.search(r"\bcurl\s*(?:\(|=)|\$\{?\w*curl\w*\}?\b|\brun_curl\b", ln) and not re.search(r"[\"']curl[\"']|https?://", ln) and re.search(r"--max-time", c)):
                add("USB-HC18", p, n, "curl/wget call has no timeout; a stalled endpoint leaves the process running indefinitely", "add --max-time/--connect-timeout (or wrap in `timeout N`)", "low")
            if py:
                m = re.search(r"\brequests\.(get|post|put|delete|head|request)\(", ln)
                if (m and "timeout" not in S()) or (re.search(r"\burlopen\(", ln) and "timeout" not in S()) :
                    add("USB-HC18", p, n, "Python network/subprocess call without timeout=", "pass timeout=", "low")
                if re.search(r"\.(read|recv)\(\s*\)", ln) and re.search(r"urlopen|resp(onse)?\.read\(\)|sock\w*\.recv\(\)|\.makefile", ln) or re.search(r"\bjson\.load\(\s*(resp|response|r|res|f)\s*\)", ln) and re.search(r"urlopen|response|resp", c):
                    add("USB-HC02", p, n, "reads a network/socket body with no size bound before parsing", "read at most N bytes (resp.read(N+1)) and reject if longer")
                if re.search(r"\brecv\(\s*\d{3,}\s*\)", ln) and re.search(r"(\+=|\.append\()", c) and re.search(r"while\s+(True|1|not|\w+)", c) and not re.search(r"len\(\s*\w*(buf|data)\w*\s*\)\s*[>]", c):
                    add("USB-HC02", p, n, "socket recv loop accumulates data with no total-size ceiling", "enforce a maximum frame/request size and close the connection when exceeded")
                _rl = re.search(r"\b(\w+)\.readline\(\s*\)", ln)
                _rf = bool(_rl) and bool(re.search(r"\bas\s+" + re.escape(_rl.group(1)) + r"\b", c)) and bool(re.search(r"(?:open\(|\.open\()[^\n]*\bas\s+" + re.escape(_rl.group(1)) + r"\b", c))   # receiver is a regular file opened here, not a socket
                if not _rf and re.search(r"\.readline\(\s*\)", ln) and re.search(r"makefile|socket|conn\b|client", c) and re.search(r"AF_UNIX|socket\.socket|makefile", c):
                    add("USB-HC02", p, n, "socket readline() without a length limit (unbounded request line)", "use readline(N) and reject lines that reach N")
            # ---------- H03 QML XHR
            if isqml and re.search(r"\bJSON\.parse\(\s*\w+\.responseText\s*\)|\bresponseText\b", ln) and "XMLHttpRequest" in c and not re.search(r"responseText\.length|\.length\s*[>]|MAX_|maxBytes|getResponseHeader\(\s*[\"']content-length", c, re.I):
                add("USB-HC03", p, n, "XMLHttpRequest response is parsed/used with no length check", "reject responses over a fixed byte limit before JSON.parse (or fetch through a size-capped curl)")
            # ---------- H04 predictable tmp
            if not re.search(r"mktemp|tempfile|XDG_RUNTIME_DIR/\$|\$\(\s*mktemp", ln):
                m = (re.search(r"(?:>>?|\btee(?:\s+-a)?|\bcp|\bmv|-o|--output|open\(\s*f?|write_text|\.writeFile|setText|FileView[^\n]*path\s*:)\s*[\(=]?\s*[\"']?(?:/tmp|\$\{?TMPDIR(?::-/tmp)?\}?|\$\{XDG_RUNTIME_DIR:-/tmp\}|\$\{?XDG_RUNTIME_DIR\}?)/[\w.${}-]+", ln)
                     or re.search(r"[\"'`]/tmp/[\w.-]+(?:\.(?:json|txt|log|sh|lock|pid|png|jpg|state|tmp|cache|sock|fifo)|\b)[\"'`]", ln) and re.search(r"write|open\(|>|tee|mv|cp|\bln\b|touch|mkfifo|FileView|setText|path", ln)
                     or re.search(r"\.tmp\.\$\$|\btmp\.\$\$|\$\$\.tmp|/tmp/[\w.-]*\$\$", ln)
                     or re.search(r"\bmkfifo\s+[\"']?(?:/tmp|\$)", ln))
                if m: add("USB-HC04", p, n, f"predictable shared path `{m.group(0).strip()[:50]}` can be pre-created as a symlink/FIFO by another process", "use mktemp or a 0700 per-user dir under $XDG_RUNTIME_DIR; open with O_NOFOLLOW|O_EXCL")
            # ---------- H05 perms
            m = re.search(r"\bchmod\s+(?:-R\s+)?(?:0?777|0?666|0?776|0?766|0?755\s+[\"']?/tmp|[ago]\+[rwx]*w|o\+rwx|a\+rwx)\b|\bumask\s+0{1,3}\b|\bmkdir\s+-m\s*0?7[0-7][67]\b|\bos\.chmod\([^\n]*0o?(?:777|666)|\bos\.umask\(0\)", ln)
            if m: add("USB-HC05", p, n, f"world-writable permission `{m.group(0)[:40]}`", "use 0600 files / 0700 dirs")
            # ---------- H06 symlink / rm -rf var
            m = (re.search(r"\bln\s+-[a-zA-Z]*s[a-zA-Z]*f|\bln\s+-[a-zA-Z]*f[a-zA-Z]*s", ln) if (sh or isqml) else None) or (re.search(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f?[a-zA-Z]*\s+[\"']?\$\{?[A-Za-z_]\w*\}?[\"']?(?:/[^\s\"']*)?(?:\s|$|\")", ln) if (sh or isqml) else None) 
            if m and not re.search(r"(^|/)(scripts?/(package|release|render|build|demo)[\w-]*|demo/|build[\w-]*|package[\w-]*|release[\w-]*|uninstall[\w-]*)", p) and not re.search(r"\[\s*-[zn]|:\?|:-/?tmp|set\s+-u", S()) and not (m and "rm" in m.group(0) and re.search(r"\$\{\w+:\?", ln)) and not _rm_var_safe(m.group(0), c):
                add("USB-HC06", p, n, f"`{m.group(0).strip()[:50]}`: forced symlink or recursive delete of an unvalidated variable", "refuse symlinks (test -L / O_NOFOLLOW), validate the variable and resolve with realpath before rm -rf")
            # ---------- H07 secret file written w/o private mode
            if re.search(r"(?i)" + SECRET_NAME, ln) and re.search(r"(>>?\s*[\"']?[$~/\w.{}-]+|\btee\b|write_text|\.write\(|json\.dump\(|setText\(|writeFile|FileView|shutil\.(copy|move))", ln) and not re.search(r"\$\(|\bgrep\b|\bread\b|\bcat\b\s+[\"']?[~$/]|\s-n\s|/dev/null|\becho\s+[\"'][^\"']*[\"']\s*$|\bif\b|\[\[|\[ ", ln) and not has_chmod600 and not re.search(r"(?i)keyring|secret-tool|libsecret|gnome-keyring|kwallet|\bpass\s+(insert|show)|\bgpg\b", c):
                add("USB-HC07", p, n, "a secret-bearing value is written to a file with no 0600/umask 077 in this file", "create the file with mode 0600 (umask 077 / os.open(...,0o600)) in a 0700 directory, or use the keyring")
            # ---------- H08 hardcoded creds
            if not lua:
                for pat, what in SECRET_PATS:
                    m = re.search(pat, ln)
                    if m and not PLACEHOLDER.search(m.group(0)):
                        add("USB-HC08", p, n, f"hardcoded {what}", "keep credentials out of source: keyring or a 0600 config outside the repo"); break
                else:
                    if re.search(r"(?i)Authorization[\"']?\s*[:,=]\s*[\"']?(?:Bearer|Basic|Token)\s+[A-Za-z0-9_\-+/=.]{20,}", ln) and not PLACEHOLDER.search(ln):
                        add("USB-HC08", p, n, "hardcoded Authorization header value", "do not commit credentials")
                    elif re.search(r"[?&](?:api_?key|apikey|key|token|access_token|appid|app_id)=[A-Za-z0-9_\-]{20,}(?:[\"'&\s]|$)", ln) and not PLACEHOLDER.search(ln):
                        add("USB-HC08", p, n, "API key literal embedded in a URL", "do not commit credentials")
                    elif re.search(r"https?://[^/\s:@\"']+:[^/\s@\"']{3,}@[\w.-]+", ln) and not PLACEHOLDER.search(ln) and not re.search(r"user:pass|username:password|\$|\{", ln):
                        add("USB-HC08", p, n, "credentials embedded in a URL", "do not commit credentials")
            # ---------- H09 secret in argv / URL query
            if re.search(r"(?i)" + SECRET_NAME, ln) and not re.search(r"@-|--config\s+-|-K\s+-|--data-binary\s+@-|\bstdin\b|--netrc|SplitParser|\bif\b\s*\(|\bnotify|placeholder|echoMode|label|hint|PlainText|\bisEmpty|\.length|=== ?[\"']{2}|\bTextField|\binput\b", ln):
                m = (re.search(r"(?:curl|wget|http)[^\n]*(?:-H|--header)\s*[\"']?[\"']?\s*(?:Authorization|X-[\w-]*(?:Key|Token)|Api-Key)[^\n]*(?:\$\{?\w+|\"\s*\+|`[^`]*\$\{)", S())
                     or re.search(r"(?:curl|wget)[^\n]*\s(?:-u|--user)\s+[\"']?[^\s\"']*(?:\$|\"\s*\+)", S())
                     or re.search(r"[?&](?:api_?key|apikey|key|token|access_token|password|secret)=(?:\$\{?\w+\}?|[\"']\s*\+|\{\w+\}|%s|\$\{)", ln)
                     or re.search(r"(?:command\s*:|execDetached\(|exec\(|subprocess\.\w+\(|Popen\()\s*\[[^\]\n]*(?:--(?:api[-_]?key|token|secret|password|key)\b|-p\b)[\"']?\s*,\s*[^\]\n]*(?:\.text|\bkey\b|token|secret|password|\$\{|\+)", S(), re.I)
                     or re.search(r"[\"']--(?:api[-_]?key|token|secret|password|passwd|access[-_]token|auth)[\"']\s*,\s*(?!\"\")[\w.]+", ln, re.I)
                     or re.search(r"\b(?:sshpass\s+-p|mysql\s[^\n]*-p\S|--password[= ]\S*\$)", ln))
                if m: add("USB-HC09", p, n, f"secret appears in a process argument/URL query (`{m.group(0)[:50]}`): visible in /proc/<pid>/cmdline, logs and proxies", "pass secrets on stdin (curl -K - / --config -), a 0600 file, or an environment variable set on the process only")
            # ---------- H10 insecure transport
            if not re.search(NS_URL, ln):
                m = (re.search(r"\bhttp://(?!" + LOCAL_HOST + r")[\w-]+(?:\.[\w-]+)+(?:[:/\"'`\s)]|$)", ln)
                     or re.search(r"\bcurl\b[^\n]*\s(?:-k|--insecure)\b|--no-check-certificate|verify\s*=\s*False|_create_unverified_context|rejectUnauthorized\s*:\s*false|NODE_TLS_REJECT_UNAUTHORIZED|check_hostname\s*=\s*False|ignoreSslErrors\(|--ssl-no-revoke|CURLOPT_SSL_VERIFYPEER", ln))
                if m: add("USB-HC10", p, n, f"insecure transport `{m.group(0).strip()[:50]}` (no TLS or certificate verification disabled)", "use https:// and keep certificate verification on")
            # ---------- H11 open non-literal URL
            m = re.search(r"Qt\.openUrlExternally\(\s*(?![\"'`]\s*[\w:/.-]+[\"'`]\s*\))[^)\n]*(?:[uU]rl|URL|[lL]ink|[hH]ref|[uU]ri|URI|target|modelData|model\.)[\w.]*\s*\)", ln) if isqml else None
            m = m or (re.search(r"\b(?:xdg-open|gio\s+open|sensible-browser|firefox|chromium|brave)\s+[\"']?\$\{?\w+", ln) if sh else None) or (re.search(r"\b(?:xdg-open|webbrowser\.open)\b[^\n]*(?:\{|\+|%s|\(\s*[a-z_]\w*\s*\))", ln) if py else None)
            m = m or (re.search(r"[\"'](?:xdg-open|firefox|brave|chromium)[\"'][^\n]*,\s*(?!\"\s*\])[\w.]*(?:[uU]rl|URL|[lL]ink|[hH]ref|[uU]ri|URI|target|\bu)\w*\s*\]", S()) if isqml and re.search(r"[\"'](?:xdg-open|gio|firefox|brave|chromium)[\"']", ln) else None)
            if m and not re.search(r"https?://[^\s\"']+[\"'`]\s*\)", ln) and not re.search(r"(?i)startsWith\([\"']https?|/^https?|https\?:|\^https", c):
                add("USB-HC11", p, n, f"opens a URL taken from data/config (`{m.group(0).strip()[:50]}`) without a scheme/host allowlist (file:, javascript:, custom handlers)", "validate with a strict ^https:// allowlist (and host check) before opening")
            # ---------- H12 redirects
            if (sh or isqml or py) and CURL.search(ln) and not NOT_RUN.search(ln):
                s2 = S()
                if re.search(r"\s(?:-[a-zA-Z]*L[a-zA-Z]*|--location(?:-trusted)?)\b", s2) and not re.search(r"--proto(?:-redir)?\b", s2) and re.search(r"https?://|\burl\b|\$", s2):
                    add("USB-HC12", p, n, "curl follows redirects (-L) without --proto =https/--proto-redir, so a redirect can leave HTTPS or the intended host", "add --proto '=https' --proto-redir '=https' and cap --max-redirs", "low")
            if py and re.search(r"\burlopen\(|urllib\.request\.Request\(|requests\.(get|post)\(", ln) and re.search(r"(?i)authorization|bearer|api[_-]?key|x-api-key|token", S()) and not re.search(r"HTTPRedirectHandler|allow_redirects\s*=\s*False|NoRedirect|redirect", c, re.I):
                add("USB-HC12", p, n, "authenticated request follows HTTP redirects by default and may forward credentials to another origin", "disable or pin redirects before sending Authorization/API-key headers", "medium")
            # ---------- H14 injection
            m = None
            QUOTED = r"shellQuote|shQuote|shq\(|quote\(|escapeShell|shell_quote|shlex|JSON\.stringify|replace\(\s*/'/g|\\\\'|printf %q|%q"
            if isqml:
                s2 = S()
                m = (re.search(r"[\"'](?:ba|z|da)?sh[\"']\s*,\s*[\"']-l?c[\"']\s*,\s*[^\]\n]*(?:[\"']\s*\+\s*[A-Za-z_][\w.\[\]()]*|`[^`]*\$\{\s*[A-Za-z_][\w.]*)", s2)
                     or re.search(r"[\"']hyprctl[\"']\s*,\s*[\"']dispatch[\"']\s*,\s*[^\]\n]*(?:[\"']\s*\+\s*[A-Za-z_]|`[^`]*\$\{)", s2)
                     or re.search(r"\bHyprland\.dispatch\(\s*(?:`[^`]*\$\{|[\"'][^\"']*[\"']\s*\+\s*[A-Za-z_])", ln))
                if m and re.search(QUOTED, s2): m = None
            elif sh:
                m = (re.search(r"\beval\s+[\"']?\$\{?[A-Za-z_]\w*\}?[\"']?\s*(?:$|;|\|)", ln) or re.search(r"\b(?:ba)?sh\s+-c\s+\"[^\"]*\$\{?[A-Za-z_]", ln))
                if m and re.search(QUOTED, ln): m = None
                if m:
                    v = re.search(r"\$\{?([A-Za-z_]\w*)", m.group(0))
                    if v and (_guarded(v.group(1), c) or _mktemp_var(v.group(1), c)): m = None
            elif py:
                m = (re.search(r"\bos\.(?:system|popen)\(\s*(?:f[\"']|[\"'][^\"']*[\"']\s*(?:\+|%|\.format))", ln) or re.search(r"shell\s*=\s*True", ln) and re.search(r"subprocess|Popen", S()) and re.search(r"f[\"']|\+|%|\.format", S()))
                if m and re.search(QUOTED, S()): m = None
            if m: add("USB-HC14", p, n, f"a value is spliced into a shell/Lua/eval string (`{m.group(0).strip()[:60]}`)", "pass values as separate argv elements, validate against an allowlist, or escape for the target interpreter")
            # ---------- H15 privileged
            m = (re.search(r"(?<![\w./-])(?:sudo|pkexec|doas|run0)(?:\s+-\S+)*\s+(?!-v\b)\S", ln) if not re.search(r"^\s*(?:echo|printf|notify|#)|\bsudoers?\b.*#|command\s+-v|which", ln) else None) \
                or re.search(r"[\"'](?:sudo|pkexec|doas|run0)[\"']\s*,", ln) \
                or re.search(r"\bsystemctl\s+(?!--user|--no-pager\s+--user)(?:-\S+\s+)*(?:enable|disable|start|stop|restart|mask|daemon-reload|edit)\b(?![^\n]*--user)", ln) \
                or re.search(r"(?:>>?|\btee\b(?:\s+-a)?|\bcp\b[^\n]*|\binstall\b[^\n]*|\bmv\b[^\n]*)\s*[\"']?/(?:etc|usr|boot|opt|var/lib|lib)/", ln) \
                or re.search(r"\bchmod\s+[ug]?\+s\b|\bchmod\s+[2467][0-7]{3}\b|\bsetcap\b|\bmodprobe\b|\binsmod\b|\budevadm\s+(?:control|trigger)|/dev/uinput|/dev/input/|/dev/mem\b|/proc/\w+/mem\b|/sys/(?:class|devices|kernel)/[^\n]*(?:>|tee)|\bnsenter\b|\bvisudo\b|/etc/sudoers|--privileged|\busermod\s+-a|\bgroupadd\b|\bloginctl\s+(?:enable-linger|terminate)|\bpolkit\b.*(?:rules|pkla)|\bEVIOCGRAB|\bptrace\b", ln)
            if m and not re.search(r"(?i)^\s*(?:#|//)|\bREADME|\bdocs?\b", ln): add("USB-HC15", p, n, f"privileged or system-level action (`{m.group(0).strip()[:50]}`)", "keep the plugin unprivileged; if root is unavoidable, use a fixed audited helper and polkit action, not caller-supplied paths")
            # ---------- H17 pinning
            m = (re.search(r"\b(?:curl|wget)\b[^|\n]*\|\s*(?:sudo\s+)?(?:ba|z|da)?sh\b", ln) or re.search(r"\b(?:ba)?sh\s+(?:-c\s+)?[\"']?\$\((?:curl|wget)\b|<\(\s*curl\b", ln)
                 or (re.search(r"\bgit\s+clone\b[^\n]*(?:https?://|git@)", ln) if not pinned and not re.search(r"--branch\s+v?\d|-b\s+v?\d|--depth[^\n]*--branch\s+\S+\.\d", ln) else None)
                 or (re.search(r"\b(?:pip3?|pipx|uv(?:\s+pip)?)\s+install\b(?![^\n]*(?:==|-r\s|--require-hashes|\.whl|\s-e\s))[^\n]*\s[a-zA-Z][\w.\[\]-]+\s*(?:[\"'`)]|$)", ln) if not re.search(r"\s-[-\w]*\s*(?:\$|\")?\s*$|--help|\bcommand\b|echo|notify", ln) else None)
                 or (re.search(r"\b(?:npm|pnpm|yarn|bun)\s+(?:install|i|add)\s+(?:-g\s+|--global\s+)?(?!-)[\w@/.-]+(?<!@\d)(?:\s|$)", ln) if (sh or py) and not re.search(r"@\d", ln) else None)
                 or (re.search(r"\b(?:npx|bunx|pipx\s+run|uvx)\s+(?!-)[\w@/.-]+(?<!@\d)(?:\s|$)", ln) if not re.search(r"@\d|==", ln) else None)
                 or re.search(r"\bgo\s+install\s+\S+@(?:latest|master|main)\b|\bcargo\s+install\b(?![^\n]*--(?:version|locked|rev|tag))[^\n]*(?:--git|\s[\w-]+\s*$)", ln)
                 or re.search(r"https://raw\.githubusercontent\.com/[^/\s]+/[^/\s]+/(?:main|master|HEAD)/", ln)
                 or re.search(r"github\.com/[^/\s]+/[^/\s]+/releases/latest(?:/download)?", ln) or re.search(r"api\.github\.com/repos/[^/\s]+/[^/\s]+/releases/latest", ln)
                )
            if m and not re.search(r"(?i)^\s*(?:echo|printf|notify|log|warn|die|msg)\b|\bUsage|\bhelp\b|Please install|Install with|\bnot found|\bmissing|\bcommand\s+-v|\bhint\b", ln):
                add("USB-HC17", p, n, f"fetches or installs code without an immutable pin (`{m.group(0).strip()[:60]}`)", "pin to a full commit SHA / exact version and verify a checksum or signature before executing")
            # ---------- H13 handled below (block level)
        if isqml and p.endswith(".qml"):
            for off, typ, body in _blocks(c):
                OL = _own_lines(body); own = "\n".join(t for _, t in OL)
                mt = None
                for bi, t in OL:
                    mm = re.match(r"\s*text\s*:\s*(.+?)\s*$", t)
                    if mm: mt = mm; text_i = bi; break
                if not mt: continue
                expr = mt.group(1)
                if expr in ("{", "") or expr.endswith("{"): continue
                tf = re.search(r"\btextFormat\s*:\s*([\w.]+)", own)
                ln_no = c.count("\n", 0, off) + 1 + text_i
                if LITERAL_TEXT.match(expr) or expr in ("\"\"", "''"): continue
                if not re.search(r"[A-Za-z_]\w*\.\w+|\b[a-z]\w*\b", expr): continue
                if tf and re.search(r"PlainText", tf.group(1)): continue
                if typ in ("StyledText",): continue
                if tf and re.search(r"RichText|StyledText|MarkdownText", tf.group(1)):
                    add("USB-HC13", p, ln_no, f"{typ} renders `{expr[:40]}` as {tf.group(1)}; markup in command output/files/network/other apps can inject links or resource loads", "use textFormat: Text.PlainText for non-literal text")
                elif not tf and EXT_SRC.search(c) and DATA_ID.search(expr) and not re.search(r"^\s*(?:root|parent)?\.?(?:is|has|show|count|index)\w*\s*[?!&|]", expr) and not re.search(r"Qt\.formatDateTime|toFixed|Math\.round|\.length\s*\+|Number\(|parseInt|parseFloat|toLocale|Qt\.formatTime|i18n|qsTr", expr):
                    add("USB-HC13", p, ln_no, f"{typ} binds `{expr[:40]}` with the default AutoText format; externally supplied text starting with markup is interpreted as rich text (link/image loads)", "set textFormat: Text.PlainText on every Text that shows external/untrusted data")
    ms = {k: v for k, v in MODEL_SPECS.items() if k in en}
    if ms:
        import hancore_rules_model as MR
        comp = _compiled_model_specs(en)
        for h in MR.check_model(files, comp, per_file=per_file):
            add(h["rule"], h["file"], h["line"], h["reason"] + " (model-proposed rule)", "see rule summary; validate/escape the value or pin/verify before use", "medium")
    return out
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(HERE)); import functest
    for f in check(functest.read_dir(sys.argv[1])): print(f"warn [{f['rule']}] {f['file']}:{f['line']}: {f['reason']}. Fix: {f['hint']}")
