#!/usr/bin/env python3
"""Static checks derived from the REAL Omarchy Quattro install on a reference Omarchy laptop (shell tree = basecamp/omarchy
@ c668141, verified byte-identical to /usr/share/omarchy/shell on the Dell). Returns (fails, flags) like static_checks.
  exec-unknown-binary : Process/exec argv[0] (string literal) that does not exist on the Dell and is not shipped by the plugin
  exec-undefined-arg  : argv built from a value that is undefined on the real API (e.g. bar.id, bar.themeName)
  bar-api-unknown     : widget reads bar.<x> that the real PluginBarApi does not have (always undefined at runtime)
  singleton-unknown   : Color.<x> / Style.<x> / Util.<x> / Border.<x> member that the real qs.Commons singleton lacks
  settings-undeclared : unguarded settings.<x> read of a key absent from the manifest defaults/schema
"""
import json, os, re, posixpath, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "dell_env"))
sys.path.insert(0, HERE)
from binaries import resolves, KNOWN
import refpaths
SHELL = refpaths.omarchy_root() + "/shell"   # raises ReferenceTreeMissing instead of loading empty API tables (audit D2)

def _members(path):
    with open(path) as fh: s = fh.read()   # a missing reference file is an error, never an empty member set (audit D2/D7)
    s = re.sub(r"//[^\n]*", "", s)
    m = set(re.findall(r"\bproperty\s+[\w.<>]+\s+(\w+)", s)) | set(re.findall(r"\bfunction\s+(\w+)", s)) | set(re.findall(r"\bsignal\s+(\w+)", s))
    m |= set(re.findall(r"^\s*(\w+)\s*:", s, re.M))  # grouped/attached defaults
    return m | {"objectName", "toString", "hasOwnProperty", "destroy"}
def _api():
    return {
        "bar": _members(SHELL + "/Ui/PluginBarApi.qml"),
        "Color": _members(SHELL + "/Commons/Color.qml"), "Style": _members(SHELL + "/Commons/Style.qml"),
        "Util": _members(SHELL + "/Commons/Util.qml"), "Border": _members(SHELL + "/Commons/Border.qml"),
    }
API = _api()
_empty = [k for k, v in API.items() if len(v) <= 4]   # only the 4 always-added names left -> the file parsed to nothing
if _empty: raise refpaths.ReferenceTreeMissing("reference API tables are empty for %s under %s" % (_empty, SHELL))
def _ui_types_with(prop):
    out = set()
    d = SHELL + "/Ui"
    for f in os.listdir(d) if os.path.isdir(d) else []:
        if f.endswith(".qml") and re.search(r"\bproperty\s+\w+\s+" + prop + r"\s*:\s*(null|\(\{\}\))", open(os.path.join(d, f)).read()): out.add(f[:-4])
    return out
BAR_TYPES, SETTINGS_TYPES = _ui_types_with("bar"), _ui_types_with("settings")
def root_type(body):
    m = re.search(r"^\s*([A-Z]\w*)\s*\{", re.sub(r"^\s*(import|pragma)[^\n]*", "", body, flags=re.M), re.M)
    return m.group(1) if m else None

def strip_comments(s):
    s = re.sub(r'/\*.*?\*/', '', s, flags=re.S)
    return re.sub(r'(^|[^:"\'\\])//[^\n]*', r'\1', s)

def manifest_keys(man):
    keys = set()
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("defaults", "settings") and isinstance(v, dict): keys.update(v.keys())
                if k == "schema" and isinstance(v, list):
                    for s in v:
                        if isinstance(s, dict) and "key" in s: keys.add(s["key"])
                walk(v)
        elif isinstance(o, list):
            for x in o: walk(x)
    walk(man); return keys

GUARD_AFTER = re.compile(r"^\s*(\|\||\?\?|!==?|===?|\?(?!\.)|&&|\)\s*(\|\||\?\?|\?))")
def guarded(body, start, end):
    before = body[max(0, start - 30):start]; after = body[end:end + 12]
    if re.search(r"(typeof\s+|!\s*|\bif\s*\(\s*|\(\s*)$", before) and not re.search(r"\w\s*\($", before[-3:]): return True
    if re.search(r"(\bin\s+|hasOwnProperty\()", body[end:end + 30]): return True
    if re.search(r"[A-Za-z_]\w*\(\s*$", before) and re.match(r"\s*,", after): return True   # helper(settings.x, fallback)
    return bool(GUARD_AFTER.match(after))

CMD_ARRAY = re.compile(r"(?:\bcommand\s*:\s*|\bQuickshell\.exec(?:Detached)?\s*\(\s*(?:\{\s*command\s*:\s*)?|\bexecDetached\s*\(\s*(?:\{\s*command\s*:\s*)?)\[\s*(['\"])([^'\"\n]+)\1")
SH_BUILTINS = set("exec if for while until set export cd test source eval case read trap local then umask ulimit shopt unset alias type hash wait printf echo true false command builtin declare typeset readonly return exit break continue shift getopts pushd popd dirs kill let".split())
DOC_FILES = ("README.md", "README", "readme.md", "README.txt", "INSTALL.md", "docs/README.md")
def documented_deps(files, man):
    """Words that the plugin documents (README / manifest) - external tools the user is told to install."""
    txt = " ".join(files.get(f, "") for f in DOC_FILES) + " " + json.dumps(man)
    return set(re.findall(r"[A-Za-z][\w.+-]*", txt))
def check(files, doc_deps=True, extra_bins=()):
    fails, flags = [], []
    F = lambda c, d: fails.append((c, d)); W = lambda c, d: flags.append((c, d))
    try: man = json.loads(files.get("manifest.json", ""))
    except Exception: man = None
    if not isinstance(man, dict): return [], []
    kinds = man.get("kinds") or []
    declared = manifest_keys(man)
    shipped = set(files)
    docs = documented_deps(files, man) if doc_deps else set()
    def unknown(exe):
        if resolves(exe, shipped) or exe in extra_bins: return False
        if os.path.basename(exe) in {posixpath.basename(f) for f in shipped} | {posixpath.basename(f).rsplit(".", 1)[0] for f in shipped} and "/" not in exe:
            return "plugin ships a file named like it, but it is not on PATH on the Dell"
        if exe in docs:
            W("exec-external-dep", f"runs `{exe}`: not on a stock Dell install, documented as an external dependency"); return False
        return True
    for p, c in files.items():
        if not p.endswith((".qml", ".js")) or re.search(r"(^|/)(test|tests|spec)[_./-]|_test\.|\.test\.|\.spec\.", p): continue
        body = strip_comments(c)
        # (a) exec of a binary the Dell does not have
        for m in CMD_ARRAY.finditer(body):
            exe = m.group(2).strip()
            if exe.startswith(("$", "~")) or "${" in exe: continue
            u = unknown(exe)
            if u: F("exec-unknown-binary", f"{p}: runs `{exe}` - not an Omarchy/system binary on the Dell and not shipped by the plugin" + ("" if u is True else f" ({u})"))
        # sh -c "<cmd> ..." first word
        for m in re.finditer(r"\[\s*['\"](?:/usr/bin/|/bin/)?(?:ba)?sh['\"]\s*,\s*['\"]-l?c['\"]\s*,\s*(['\"`])([A-Za-z][\w.+-]*)[\s'\"`]", body):
            w = m.group(2)
            if w not in SH_BUILTINS and unknown(w):
                F("exec-unknown-binary", f"{p}: sh -c runs `{w}` - not an Omarchy/system binary on the Dell")
        # (b, static half) argv elements built from undefined real-API members
        rt = root_type(body)
        if (rt in BAR_TYPES or re.search(r"\bproperty\s+(?:var|QtObject|Item|PluginBarApi)\s+bar\s*(?::\s*null\s*)?(?:$|;|\n)", body, re.M)) and "bar" not in kinds:
            for m in re.finditer(r"(?<![\w.])(?:root\.)?bar\.(\w+)", body):
                if m.group(1) not in API["bar"]:
                    seg = body[max(0, m.start() - 200):m.start()]
                    in_cmd = re.search(r"(command\s*:\s*\[|exec\w*\(\s*\[)[^\]]*$", seg)
                    if in_cmd: F("exec-undefined-arg", f"{p}: command argv uses bar.{m.group(1)}, which the real PluginBarApi does not provide (= 'undefined')")
                    else: W("bar-api-unknown", f"{p}: bar.{m.group(1)} is not a PluginBarApi member on Omarchy 4.0.0.alpha (always undefined)")
        # real singleton members
        if re.search(r"^\s*import\s+qs\.Commons", body, re.M):
            for m in re.finditer(r"(?<![\w.])(Color|Style|Util|Border)\.([A-Za-z_]\w*)", body):
                if m.group(2) not in API[m.group(1)]:
                    F("singleton-unknown", f"{p}: {m.group(1)}.{m.group(2)} does not exist in the real qs.Commons {m.group(1)} singleton")
        # (c) settings declared in manifest defaults
        if (rt in SETTINGS_TYPES or re.search(r"\bproperty\s+var\s+settings\b", body)) and not re.search(r"\bid\s*:\s*settings\b", body):
            for m in re.finditer(r"(?<![\w.])(?:root\.)?settings(?:\.(\w+)|\[\s*['\"](\w+)['\"]\s*\])", body):
                k = m.group(1) or m.group(2)
                if k in declared or k in ("hasOwnProperty", "id"): continue
                seg = body[max(0, m.start() - 200):m.start()]
                if re.search(r"(command\s*:\s*\[|exec\w*\(\s*\[)[^\]]*$", seg) and not guarded(body, m.start(), m.end()):
                    F("exec-undefined-arg", f"{p}: command argv uses settings.{k}, which is not declared in manifest defaults/schema (= 'undefined' on a fresh install)")
                else:
                    W("settings-undeclared", f"{p}: settings.{k} not declared in manifest defaults/schema" + ("" if guarded(body, m.start(), m.end()) else " (read without a fallback)"))
    def dd(xs):
        seen, out = set(), []
        for x in xs:
            if x not in seen: seen.add(x); out.append(x)
        return out
    return dd(fails), dd(flags)

if __name__ == "__main__":
    sys.path.insert(0, HERE); import functest
    print(json.dumps(check(functest.read_dir(sys.argv[1])), indent=1))
