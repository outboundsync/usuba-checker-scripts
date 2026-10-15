"""Candidate Checker rules USB-JV01..JV09 derived from jankeesvw's fix history (data-driven, regex only; advisory).
check(files) -> [dict(rule, file, line, reason, hint)]. Not wired into functest (that tree is owned by other branches); see docs/jankeesvw-history.md for how to port."""
import re
SECRET_VAR = r"(?!(?:has|is|use|n|max|page|next|sync)_)(?!\w*(?:keyring|keymap|keybind))[A-Za-z_]*(?:key|token|secret|pass(?:word)?|bearer|cookie|auth|refresh|rt)[A-Za-z_]*"
SH_EXT = (".sh", ".bash")
def _kind(p, c):
    if p.endswith(SH_EXT): return "sh"
    if p.endswith(".py"): return "py"
    if p.endswith((".qml", ".js")): return "qml"
    if "." not in p.rsplit("/", 1)[-1] and c.startswith("#!"):
        h = c.split("\n", 1)[0]
        return "py" if "python" in h else "sh" if re.search(r"\b(ba|z|da)?sh\b", h) else None
    return None
def _strip(l, kind):
    s = l.strip()
    if s.startswith(("#", "//", "*", "/*")) and not s.startswith("#!"): return ""
    return l
RULES = {
 "USB-JV01": "secret passed in a curl header/auth argument (visible in /proc/PID/cmdline); feed it on stdin (`curl -K -` / `-H @-`)",
 "USB-JV02": "jq `--arg`/`--argjson` carries a secret-named value (argv is world-readable); use `--rawfile`/stdin or `env.NAME` inside jq",
 "USB-JV03": "secret exported into the environment of a long-lived process (readable by every process of the same account via /proc/PID/environ)",
 "USB-JV04": "urllib `urlopen` on a non-literal URL follows redirects, so an https feed can be redirected to http; install an opener that refuses scheme changes",
 "USB-JV05": "external value passed as the first positional argument to a media/opener tool with no `--`; a value starting with `-` becomes an option",
 "USB-JV06": "value taken from jq/curl output used in `$(( ))` or `[[ -gt ]]` with no numeric check; bash evaluates `a[$(cmd)]` in arithmetic context",
 "USB-JV07": "QML uses the unqualified `Color.` singleton next to `import qs.Commons`; Qt 6.12 ships its own `Color`, so it must be read as `Commons.Color` (version-dependent)",
 "USB-JV08": "`iconComponent:` content with text/badge; the shell scales an iconComponent to bar-icon size (Omarchy shell of 2026-10-13), so counts become unreadable (version-dependent)",
 "USB-JV09": "tooltipText built by concatenating external strings; the tooltip is rich text, so markup in the data is interpreted (wrap in a plain-text escape)",
}
def check(files):
    out = []
    def add(r, p, n, extra=""): out.append(dict(rule=r, file=p, line=n, reason=RULES[r] + extra, hint=""))
    for p, c in files.items():
        k = _kind(p, c)
        if not k or len(c) > 400_000: continue
        lines = c.split("\n")
        if k == "sh":
            assigned_ext = set()
            i = 0
            while i < len(lines):   # JV05 on logical lines (backslash continuations joined; reported at the first physical line)
                j = i; joined = lines[i]
                while joined.rstrip().endswith("\\") and j + 1 < len(lines): j += 1; joined = joined.rstrip()[:-1] + " " + lines[j].strip()
                jl = _strip(joined, k)
                if jl and re.search(r"(?:^|[\s;&|(])(?:exec\s+)?(?:mpv|xdg-open|ffplay|vlc)\s+.*[\"']?\$\{?\w*(?:url|uri|link|stream|target|src)\w*[\"']?\s*(?:$|[;&|])", jl, re.I) and " -- " not in jl: add("USB-JV05", p, i + 1)
                i = j + 1
            for i, l in enumerate(lines, 1):
                l = _strip(l, k)
                if not l: continue
                m = re.match(r"\s*(?:local\s+|declare\s+)?(\w+)=\$\((?=.*\b(?:jq|curl|cat)\b)", l)
                if m: assigned_ext.add(m.group(1))
                if re.search(r"\bcurl\b", l) and re.search(r"(?:-H|--header|-u|--user)\s+[\"']?[^\"'\n]*\$\{?" + SECRET_VAR, l, re.I) and "@-" not in l: add("USB-JV01", p, i)
                elif re.search(r"(?:-H|--header)\s+\"[^\"]*\$\{?" + SECRET_VAR + r"[^\"]*\"", l, re.I) and not re.search(r"@-|curl\s+.*-K\s+-|--config\s+-", l): add("USB-JV01", p, i)
                if re.search(r"\bjq\b.*--arg(?:json)?\s+\w+\s+[\"']?\$\{?" + SECRET_VAR, l, re.I): add("USB-JV02", p, i)
                if re.match(r"\s*export\s+(?!\w*KEYRING)\w*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD)\w*=", l): add("USB-JV03", p, i)
                if re.search(r"\$\(\(.*\$\(.*\b(?:jq|curl)\b", l) and not re.search(r"number_or|\bint\(|=~", l): add("USB-JV06", p, i)
                arith = l[l.index("$(("):l.index("))", l.index("$((")) + 2] if "$((" in l and "))" in l[l.index("$(("):] else ""
                for v in assigned_ext:
                    if (re.search(r"(?<![\w$-])\$?\{?" + v + r"\b", arith) or re.search(r"\[\[\s+\"?\$\{?" + v + r"\}?\"?\s+-(?:gt|lt|ge|le|eq|ne)\b", l)) and "number_or" not in l and not re.search(r"\[\[\s+\"?\$\{?" + v + r"\}?\"?\s+=~\s+\^?\[?0-9|case\s+\"?\$\{?" + v + r"\}?\"?\s+in\s+\*\[!0-9\]|" + v + r"=\$\(number_or|" + v + r"=\$\(\(", c): add("USB-JV06", p, i)
        if k == "py":
            if re.search(r"urllib\.request", c) and not re.search(r"HTTPRedirectHandler|build_opener", c):
                for i, l in enumerate(lines, 1):
                    if re.search(r"\burlopen\(\s*(?!['\"])\w", _strip(l, k)): add("USB-JV04", p, i); break
            for i, l in enumerate(lines, 1):
                l = _strip(l, k)
                if re.search(r"\bjq\b.*--arg", l) and re.search(SECRET_VAR, l, re.I): add("USB-JV02", p, i)
        if k == "qml":
            if re.search(r"^\s*import\s+qs\.Commons\s*$", c, re.M) and not re.search(r"import\s+qs\.Commons\s+as\s+Commons", c) and not re.search(r"Commons\.Color", c):
                for i, l in enumerate(lines, 1):
                    if re.search(r"(?<![\w.])Color\.(?:foreground|background|accent|bar|border|surface|primary|secondary|warn|error|success|pick|mix|alpha|text)\w*", _strip(l, k)): add("USB-JV07", p, i); break
            for i, l in enumerate(lines, 1):
                l = _strip(l, k)
                if re.match(r"\s*iconComponent\s*:", l):
                    blk = "\n".join(lines[i - 1:i + 40])
                    if re.search(r"\bText\s*\{", blk): add("USB-JV08", p, i); break
            for i, l in enumerate(lines, 1):
                l = _strip(l, k)
                if re.match(r"\s*tooltipText\s*:", l):
                    blk = lines[i - 1:i + 8]; end = next((n for n, x in enumerate(blk[1:], 1) if re.match(r"\s*[a-zA-Z]+\s*:", x) and not x.strip().startswith(("?", ":"))), len(blk))
                    seg = blk[:end]
                    for n, x in enumerate(seg):
                        if re.search(r"\+\s*[\w.]*\b(?:name|text|title|summary|error\w*|label|body)\b", _strip(x, k), re.I) and not re.search(r"plain|escape|PlainText|stripHtml|encodeHtml", "\n".join(seg)): add("USB-JV09", p, i + n); break
    return out
