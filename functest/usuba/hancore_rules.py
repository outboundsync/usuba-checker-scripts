#!/usr/bin/env python3
"""HANCORE-derived review rules (USB-W01..W10). Every rule is a WARNING (severity "medium"/"low"), never a fail:
the only hard-fail safety rule stays USB-S03 (clearly destructive commands). Rules in EXPERIMENTAL are off by default
(their measured precision against HANCORE's findings was too low); pass experimental=True to run them.
check(files, experimental=False) -> [dict(rule, severity, file, reason, hint, line)]"""
import re, os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__))
try:
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "dell_env")); from binaries import KNOWN
except Exception: KNOWN = set()
CODE_EXT = (".qml", ".js", ".mjs", ".sh", ".bash", ".zsh", ".py", ".lua")
SHELLY = (".sh", ".bash", ".zsh")
DOC_RE = re.compile(r"(?i)(^|/)(readme[^/]*|install[^/]*\.md|docs?/.*|manifest\.json|pkgbuild|deps?[^/]*|requirements[^/]*\.txt)$")
SKIP_PATH = re.compile(r"(^|/)(tests?|spec|examples?|\.github|node_modules|vendor)/|_test\.|\.test\.|\.spec\.")
EXPERIMENTAL = {"USB-W01", "USB-W02", "USB-W03", "USB-W04", "USB-W06", "USB-W07", "USB-W08", "USB-W09", "USB-W10"}   # set from hancore/measure_rules.py results (see STANDARD.md)

def _lines(c, p):
    """(lineno, line) with full-line comments dropped and trailing // or # comments trimmed (best effort)."""
    sh = p.endswith(SHELLY + (".py",))
    for i, ln in enumerate(c.splitlines(), 1):
        s = ln.strip()
        if len(s) > 1000: continue   # minified/generated lines
        if not s or s.startswith(("//", "*", "/*", "--" if p.endswith(".lua") else "\0")) or (sh and s.startswith("#")): continue
        if not sh and " //" in ln and "://" not in ln.split(" //")[0][-3:]: ln = ln.split(" //")[0]
        yield i, ln

SECRET_PATS = [
    (r"\bgh[pousr]_[A-Za-z0-9]{36,}\b", "GitHub token"), (r"\bgithub_pat_[A-Za-z0-9_]{50,}\b", "GitHub PAT"),
    (r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}\b", "OpenAI/Anthropic-style key"), (r"\bAKIA[0-9A-Z]{16}\b", "AWS access key"),
    (r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b", "Slack token"), (r"\bAIza[0-9A-Za-z_-]{35}\b", "Google API key"),
    (r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----", "private key"),
    (r"(?i)\b(?:api[_-]?key|apikey|secret|token|password|passwd|client[_-]?secret|auth)\w*\s*[:=]\s*[\"'`]([A-Za-z0-9_\-+/=.]{16,})[\"'`]", "literal credential"),
]
PLACEHOLDER = re.compile(r"(?i)your|example|xxx|placeholder|changeme|dummy|test|sample|<|\$\{|process\.env|getenv")

def check(files, experimental=False):
    out = []
    def add(rule, sev, f, line, reason, hint):
        if rule in EXPERIMENTAL and not experimental: return
        out.append(dict(rule=rule, severity=sev, file=f, line=line, reason=reason, hint=hint))
    code = {p: c for p, c in files.items() if p.endswith(CODE_EXT) and not SKIP_PATH.search(p)}
    docs = " ".join(c for p, c in files.items() if DOC_RE.search(p)).lower()
    seen = set()
    def once(rule, p):
        k = (rule, p)
        if k in seen: return False
        seen.add(k); return True
    for p, c in code.items():
        qml = p.endswith((".qml", ".js", ".mjs")); sh = p.endswith(SHELLY)
        pinned = re.search(r"(?m)^\s*git\s+(-C\s+\S+\s+)?(checkout|reset --hard)\s+[0-9a-f]{7,40}\b", c)
        for n, ln in _lines(c, p):
            # W02 hardcoded secrets
            for pat, what in SECRET_PATS:
                m = re.search(pat, ln)
                if m and not PLACEHOLDER.search(m.group(0)) and once("USB-W02", p):
                    add("USB-W02", "medium", p, n, f"line {n}: hardcoded {what} in source", "read secrets from the user's keyring (secret-tool) or a 0600 config file outside the plugin, never commit them")
            # W03 unpinned remote code
            m = (re.search(r"\b(curl|wget)\b[^|\n]*\|\s*(sudo\s+)?(ba|z|da)?sh\b", ln) or re.search(r"\b(?:ba)?sh\s+(?:-c\s+)?[\"']?\$\((?:curl|wget)\b", ln)
                 or (re.search(r"\bgit\s+clone\b(?![^\n]*(--branch|-b)\s+v?\d)[^\n]*https?://", ln) if not pinned else None)
                 or re.search(r"\b(?:pip|pipx|uv)\s+install\b[^\n]*git\+https?://[^\s@]+(?:\s|$)", ln)
                 or re.search(r"https://raw\.githubusercontent\.com/[^/\s]+/[^/\s]+/(main|master|HEAD)/", ln)
                 or re.search(r"/releases/latest/download/", ln) or (sh and re.search(r"\b(npx|bunx)\s+(?!-)[\w@/.-]+(?!@\d)", ln)))
            if m and once("USB-W03", p):
                add("USB-W03", "medium", p, n, f"line {n}: runs or installs remote code that is not pinned to an immutable ref (`{m.group(0)[:60]}`)", "pin to a full commit SHA or a versioned release and verify a checksum; never pipe a download into a shell")
            # W04 unsafe file ops
            m = (re.search(r"\bchmod\s+(-R\s+)?(0?777|0?666|[ao]\+w|o\+rwx)\b", ln) or re.search(r"\bln\s+-[a-zA-Z]*s[a-zA-Z]*f\b|\bln\s+-[a-zA-Z]*f[a-zA-Z]*s\b", ln)
                 or re.search(r"[>]\s*[\"']?/tmp/[\w.-]+[\"']?(\s|$)", ln) or re.search(r"[\"'`]/tmp/[\w.-]+\.(json|txt|log|sh|lock|pid|png|state)[\"'`]", ln)
                 or (sh and re.search(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f?\s+[\"']?\$\{?\w+\}?[\"']?/?(\s|$|\")", ln)))
            if m and once("USB-W04", p):
                add("USB-W04", "medium", p, n, f"line {n}: unsafe file operation `{m.group(0).strip()[:60]}` (world-writable mode, forced symlink, predictable /tmp path, or rm -rf on an unchecked variable)", "use mktemp / $XDG_RUNTIME_DIR, 0600/0700 modes, refuse symlinks (O_NOFOLLOW or test -L), and validate a variable before rm -rf")
            # W05 privileged commands
            m = (re.search(r"(^|[\s\"'`;(|&])(sudo|pkexec|doas|run0)(\s|[\"'`],)", ln) or re.search(r"\bsystemctl\s+(?!--user)(enable|disable|start|stop|restart|mask)\b", ln)
                 or re.search(r"(>|\btee\b(\s+-a)?)\s*[\"']?/(etc|usr|boot|opt)/", ln) or re.search(r"\bchmod\s+[ug]?\+s\b|\bchmod\s+[4-7][0-7]{3}\b", ln))
            if m and once("USB-W05", p):
                add("USB-W05", "medium", p, n, f"line {n}: privileged/system-level action `{m.group(0).strip()[:50]}`", "keep the plugin unprivileged; document manual root steps in the README instead of escalating from the shell")
            # W06 rich text bound to data
            if qml:
                m = re.search(r"\btextFormat\s*:\s*Text\.(RichText|StyledText|MarkdownText)\b", ln)
                if m and once("USB-W06", p):
                    add("USB-W06", "medium", p, n, f"line {n}: Text.{m.group(1)} renders markup; if its text comes from command output, files, network or other apps it can inject links/images", "use textFormat: Text.PlainText for any non-literal text (or escape <, >, & before display)")
            # W07 shell / Lua injection: interpolation into sh -c / eval / hyprctl dispatch strings
            if qml:
                m = (re.search(r"[\"'](?:ba|z)?sh[\"']\s*,\s*[\"']-l?c[\"']\s*,\s*(?:[\"'][^\"'\n]*[\"']\s*\+|`[^`\n]*\$\{)", ln)
                     or re.search(r"\b(?:execDetached|exec)\s*\(\s*\[?\s*[\"'`](?:hyprctl|omarchy-\S+)[^\"'`]*[\"'`]\s*\+", ln)
                     or re.search(r"[\"']hyprctl[\"']\s*,\s*[\"']dispatch[\"']\s*,\s*[^\]\n]*\+", ln))
            elif sh:
                m = re.search(r"\beval\s+[\"']?\$|\b(?:ba)?sh\s+-c\s+\"[^\"]*\$\{?\w", ln)
            elif p.endswith(".py"):
                m = re.search(r"\b(os\.system|os\.popen)\s*\(\s*f?[\"'][^\n]*(\{|%s|\"\s*\+)|shell\s*=\s*True[^\n]*$", ln) if re.search(r"os\.system|os\.popen|shell\s*=\s*True", ln) else None
            else: m = None
            if m and once("USB-W07", p):
                add("USB-W07", "medium", p, n, f"line {n}: a variable is interpolated into a shell/Lua command string (`{m.group(0)[:60]}`)", "pass values as separate argv elements (Process command: [prog, arg]) or quote/escape them; never build sh -c / hyprctl dispatch strings from data")
            # W08 missing timeouts (experimental)
            m = re.search(r"\b(curl|wget)\b(?![^\n]*(--max-time|-m\s*\d|--connect-timeout|--timeout|-T\s*\d))", ln) if (sh or qml or p.endswith(".py")) and not re.search(r"\btimeout\s+\d", ln) else None
            if not m and p.endswith(".py"): m = re.search(r"\brequests\.(get|post|put|delete|head)\((?![^\n]*timeout=)", ln) or re.search(r"\burlopen\((?![^\n]*timeout)", ln)
            if m and re.search(r"curl|wget", m.group(0)) and not re.search(r"[\"'`]\s*(curl|wget)|^\s*(curl|wget)|\|\s*(curl|wget)|\$\((curl|wget)", ln): m = None
            if m and once("USB-W08", p):
                add("USB-W08", "low", p, n, f"line {n}: network call without a timeout (`{m.group(0)[:40]}`)", "add --max-time / --connect-timeout (curl), timeout= (Python), xhr.timeout (QML), or wrap in `timeout 10`")
            # W09 non-https URLs
            m = re.search(r"\bhttp://(?!localhost|127\.|0\.0\.0\.0|\[::1\]|192\.168\.|10\.|172\.(1[6-9]|2\d|3[01])\.|[\w.-]*\.local\b|www\.w3\.org|\$|\{|schemas?\.)[\w.-]+\.[a-z]{2,}", ln)
            if m and once("USB-W09", p):
                add("USB-W09", "medium", p, n, f"line {n}: plain-http URL `{m.group(0)}` (no TLS)", "use https:// for remote endpoints")
        if p.endswith(".qml"):
            # W06b: XMLHttpRequest without timeout -> W08 (experimental)
            if "XMLHttpRequest" in c and not re.search(r"\.timeout\s*=", c) and once("USB-W08", p):
                add("USB-W08", "low", p, 0, "XMLHttpRequest without xhr.timeout", "set xhr.timeout and handle ontimeout")
            # W10 unbounded input (experimental): collectors / FileView with no size handling anywhere in the file
            if re.search(r"\b(StdioCollector|FileView|SplitParser)\b", c) and not re.search(r"head\s+-c|\.slice\(|\.substring\(|maxLength|MAX_\w+|\bsize\b.*[<>]|length\s*>", c) and once("USB-W10", p):
                add("USB-W10", "low", p, 0, "reads command output or a file with no size cap", "cap reads (head -c N, slice after a byte limit) before parsing or displaying")
        # W04b symlink-following writes in QML FileView setText to fixed home paths are covered by W04 regexes in scripts only
    # W01 undeclared dependency (experimental): program invoked but not on the base Dell PATH and not mentioned in README/manifest/PKGBUILD
    shipped = {os.path.basename(p) for p in files}
    for p, c in code.items():
        progs = set(re.findall(r"(?:command\s*:\s*\[|exec(?:Detached)?\s*\(\s*\[)\s*[\"']([\w.+-]+)[\"']", c))
        if p.endswith(SHELLY):
            progs |= {w for w in re.findall(r"(?m)^\s*(?:if\s+!?\s*)?([a-z][\w.+-]{2,})\s", c) if w not in SH_BUILTINS}
        for g in sorted(progs):
            if KNOWN and (g in KNOWN or g in shipped or g in SH_BUILTINS): continue
            if not KNOWN and g in SH_BUILTINS: continue
            if g.lower() in docs: continue
            if once("USB-W01", p):
                add("USB-W01", "low", p, 0, f"runs `{g}`, which is not part of a stock Omarchy install and is not listed as a dependency in the README/manifest", "list every external program in the README (with the pacman/AUR package) and check `command -v` before use")
    return out
SH_BUILTINS = set("if then else elif fi for while until do done case esac function return local export echo printf read set unset shift cd pwd test true false exit source trap wait eval exec break continue declare readonly let type command alias printf mkdir rm cp mv ln cat grep sed awk cut tr sort uniq head tail wc find xargs chmod chown touch date sleep kill env basename dirname realpath readlink stat jq bash sh tee mktemp printf".split())
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(HERE)); import functest
    for f in check(functest.read_dir(sys.argv[1]), experimental="--experimental" in sys.argv): print(f"warn [{f['rule']}] {f['file']}: {f['reason']}. Fix: {f['hint']}")
