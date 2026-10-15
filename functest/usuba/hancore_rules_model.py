"""Engine for model-proposed USB-H19+ rules (data-driven specs; see model_rules_v3.json). check_model(files, rules) -> hits
(rule, file, line, reason). A spec is data only: line_regex + optional exclude/file-level/window conditions; no code from the model is executed."""
import re, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from hancore_rules import _lines, SKIP_PATH
EXTS = {".sh": (".sh", ".bash", ".zsh"), ".py": (".py",), ".qml": (".qml",), ".js": (".js", ".mjs"), ".lua": (".lua",)}
def _kind(p, c):
    for k, es in EXTS.items():
        if p.endswith(es): return k
    if not os.path.splitext(p)[1] and c.startswith("#!"):
        h = c.split("\n", 1)[0]
        if re.search(r"\b(ba|z|da)?sh\b", h): return ".sh"
        if "python" in h: return ".py"
    return None
def compile_spec(s):
    """returns compiled dict or raises; rejects slow (catastrophic) regexes."""
    fl = re.I if s.get("ignore_case") else 0
    out = dict(s)
    for k in ("line_regex", "line_exclude_regex", "file_must_contain_regex", "file_must_not_contain_regex", "window_must_not_contain_regex"):
        v = s.get(k)
        out[k + "_c"] = re.compile(v, fl | re.M) if v else None
    if not out["line_regex_c"]: raise ValueError("no line_regex")
    for k in [k for k in out if k.endswith("_c") and out[k]]:
        for bad in ("a" * 3000, "a, " * 1000, ("x" * 20 + " ") * 150, "{" * 2000, "$" * 2000 + " "):
            t = time.time(); out[k].search(bad)
            if time.time() - t > 0.05: raise ValueError("slow regex " + k)
    if out["line_regex_c"].search(""): raise ValueError("matches empty")
    return out
def check_model(files, rules, per_file=50):
    """rules: {id: compiled spec dict (compile_spec) + 'summary'}"""
    hits = []
    for p, c in files.items():
        if SKIP_PATH.search(p) or len(c) > 400_000: continue
        k = _kind(p, c)
        if not k: continue
        active = {rid: s for rid, s in rules.items() if k in s.get("file_types", [])}
        if not active: continue
        todo = {}
        for rid, s in active.items():
            if s["file_must_contain_regex_c"] and not s["file_must_contain_regex_c"].search(c): continue
            if s["file_must_not_contain_regex_c"] and s["file_must_not_contain_regex_c"].search(c): continue
            todo[rid] = s
        if not todo: continue
        L = list(_lines(c, p)); cnt = {}
        for i, (n, ln) in enumerate(L):
            for rid, s in todo.items():
                if cnt.get(rid, 0) >= per_file: continue
                if not s["line_regex_c"].search(ln): continue
                if s["line_exclude_regex_c"] and s["line_exclude_regex_c"].search(ln): continue
                if s["window_must_not_contain_regex_c"] and s["window_must_not_contain_regex_c"].search(" ".join(x[1] for x in L[i:i + 6])): continue
                cnt[rid] = cnt.get(rid, 0) + 1
                hits.append(dict(rule=rid, file=p, line=max(1, n), reason=s.get("summary", "")[:120]))
    return hits
