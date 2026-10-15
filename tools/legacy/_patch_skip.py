# one-off patch applied in v3-fixes (kept for provenance); idempotent guard below
s=open('hancore_rules_v2.py').read()
if "def vendored_prefixes" in s: raise SystemExit("already applied")
def rep(a,b):
    global s
    assert a in s, a[:60]; s=s.replace(a,b,1)
rep("def _win(L, i, n=6):", '''VENDOR_DIR = re.compile(r"(^|/)(vendor|vendored|third[_-]?party|upstream|external|extern|deps)(/|$)", re.I)
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
            for m in re.finditer(r"`?((?:[\\w.-]+/)+)`?", c):
                d = m.group(1)
                if any(q.startswith(d) for q in files) and not d.startswith(("docs/", "http")) and len(d) > 2: out.add(d)
    return out
def is_vendored(p, pref): return bool(VENDOR_DIR.search(p)) or any(p.startswith(x) for x in pref)
def _guarded(var, c):
    """variable validated by a regex/case guard somewhere in the script ([[ $v =~ ^...$ ]], case $v in)"""
    v = re.escape(var)
    return bool(re.search(r"\\[\\[\\s*\\"?\\$\\{?" + v + r"\\}?\\"?\\s*=~\\s*\\^|case\\s+\\"?\\$\\{?" + v + r"\\}?\\"?\\s+in", c))
def _mktemp_var(var, c):
    v = re.escape(var); return bool(re.search(r"\\b" + v + r"=[\\"']?\\$\\(\\s*mktemp\\b|\\b" + v + r"=[\\"']?`\\s*mktemp\\b", c))
def _rm_var_safe(txt, c):
    v = re.search(r"\\$\\{?([A-Za-z_]\\w*)", txt)
    return bool(v) and "rm" in txt and (_mktemp_var(v.group(1), c) or _guarded(v.group(1), c))
def _win(L, i, n=6):''')
rep('''    code = {p: c for p, c in files.items() if (p.endswith(CODE_EXT) or (not os.path.splitext(p)[1] and c.startswith("#!"))) and not SKIP_PATH.search(p) and len(c) < 400_000}''',
'''    vend = vendored_prefixes(files)
    code = {p: c for p, c in files.items() if (p.endswith(CODE_EXT) or (not os.path.splitext(p)[1] and c.startswith("#!"))) and not SKIP_PATH.search(p) and len(c) < 400_000 and not is_vendored(p, vend)}''')
rep('''and not re.search(r"[|]\\s*head\\s+-c|--max-filesize|--limit-rate|--quota", S()):
                if not (py''','''and not re.search(r"[|]\\s*head\\s+-c|--max-filesize|--limit-rate|--quota", S()) and not re.search(r"(?:^|\\s)(?:-o|--output)[ =]*[\\"']?/dev/null\\b|>\\s*/dev/null", S()):
                if not (py''')
rep('''and not has_timeout_any:
                add("USB-HC18"''','''and not has_timeout_any and not (re.search(r"\\bcurl\\s*(?:\\(|=)|\\$\\{?\\w*curl\\w*\\}?\\b|\\brun_curl\\b", ln) and not re.search(r"[\\"']curl[\\"']|https?://", ln) and re.search(r"--max-time", c)):
                add("USB-HC18"''')
rep('''if re.search(r"\\.readline\\(\\s*\\)", ln) and re.search(r"makefile|socket|conn\\b|client", c)''','''_rl = re.search(r"\\b(\\w+)\\.readline\\(\\s*\\)", ln)
                _rf = bool(_rl) and bool(re.search(r"\\bas\\s+" + re.escape(_rl.group(1)) + r"\\b", c)) and bool(re.search(r"(?:open\\(|\\.open\\()[^\\n]*\\bas\\s+" + re.escape(_rl.group(1)) + r"\\b", c))   # receiver is a regular file opened here, not a socket
                if not _rf and re.search(r"\\.readline\\(\\s*\\)", ln) and re.search(r"makefile|socket|conn\\b|client", c)''')
rep('''and not (m and "rm" in m.group(0) and re.search(r"\\$\\{\\w+:\\?", ln)):''','''and not (m and "rm" in m.group(0) and re.search(r"\\$\\{\\w+:\\?", ln)) and not _rm_var_safe(m.group(0), c):''')
rep('''                if m and re.search(QUOTED, ln): m = None
            elif py:''','''                if m and re.search(QUOTED, ln): m = None
                if m:
                    v = re.search(r"\\$\\{?([A-Za-z_]\\w*)", m.group(0))
                    if v and (_guarded(v.group(1), c) or _mktemp_var(v.group(1), c)): m = None
            elif py:''')
open('hancore_rules_v2.py','w').write(s)
import json
p='model_rules_v3.json'; d=json.load(open(p))
sp=d['rules']['USB-HC24']; sp['line_exclude_regex']=r"^\s*#|\bhyprctl\s+(?:-\S+\s+)*eval\b"; sp['file_must_not_contain_regex']=r"\[\[\s*\"?\$\{?\w+\}?\"?\s*=~\s*\^"
sp['v3_fixes_note']="skips hyprctl eval (Lua, not shell eval) and files that regex-guard their variables with [[ $v =~ ^...$ ]] (winners follow-up, docs/V3_FIXES.md)"
json.dump(d,open(p,'w'),indent=1)
# (second step, applied by hand in v3-fixes: _cont() continuation window for the HC01 /dev/null skip; see hancore_rules_v2.py)
