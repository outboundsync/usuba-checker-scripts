#!/usr/bin/env python3
"""Faithful Python port of basecamp/omarchy bin/omarchy-plugin-validate @ 9480d1b6 (MIT, (c) DHH).
Also used to validate in-memory dataset examples ({path: content}). Exit 0 + silent = pass."""
import json, os, re, sys, tempfile
KIND_EP = {"bar":"bar","bar-widget":"barWidget","menu":"menu","overlay":"overlay","panel":"panel","service":"service"}
def validate_dir(d):
    m = os.path.join(d, "manifest.json")
    if not os.path.isdir(d): return f"plugin folder not found: {d}"
    if not os.path.isfile(m): return f"missing manifest.json in {d}"
    try: j = json.load(open(m))
    except Exception: return f"manifest.json is not valid JSON: {m}"
    if not isinstance(j, dict): return f"unsupported or missing schemaVersion (expected 1) in {m}"
    sv = j.get("schemaVersion")
    if not (type(sv) in (int, float) and not isinstance(sv, bool) and sv == 1): return f"unsupported or missing schemaVersion (expected 1) in {m}"
    for f in ["id","name","version","kinds","entryPoints"]:
        if f not in j: return f"manifest missing required field '{f}'"
    i = j["id"]; i = "" if i is None else (i if isinstance(i,str) else json.dumps(i) if not isinstance(i,bool) else str(i).lower())
    if not i: return "manifest 'id' is empty"
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", i) or ".." in i: return f"invalid plugin id '{i}'"
    if i.startswith("omarchy."): return f"plugin id '{i}' uses the reserved omarchy.* namespace"
    k = j["kinds"]
    if not (isinstance(k, list) and k): return "'kinds' must be a non-empty array"
    ep = j["entryPoints"]
    if not isinstance(ep, dict): return "'entryPoints' must be an object"
    bw = j.get("barWidget")
    if isinstance(bw, dict) and "defaultSection" in bw and bw["defaultSection"] not in ("left","center","right"):
        return "'barWidget.defaultSection' must be left, center, or right"
    for v in ep.values():
        v = v if isinstance(v, str) else ("" if v is None else json.dumps(v))
        if not v: return "entry point path is empty"
        if "\n" in v: return "entry point may not contain a newline"
        if v.startswith("/"): return f"entry point must be a relative path: '{v}'"
        if ".." in v: return f"entry point may not contain '..': '{v}'"
        if not os.path.isfile(os.path.join(d, v)): return f"entry point file not found: '{v}'"
    for kind, key in KIND_EP.items():
        if kind in k and key not in ep: return f"kind '{kind}' requires an 'entryPoints.{key}' to load"
    for root, dirs, files in os.walk(d):
        if ".git" in dirs: dirs.remove(".git")
        for n in dirs + files:
            p = os.path.join(root, n)
            if os.path.islink(p): return f"symlinks are not allowed inside a plugin folder: {p}"
    return None
def validate_files(files, symlinks=None):
    """files: {relpath: text}; symlinks: {relpath: target}"""
    with tempfile.TemporaryDirectory() as t:
        for p, c in files.items():
            fp = os.path.join(t, p); os.makedirs(os.path.dirname(fp), exist_ok=True); open(fp, "w").write(c)
        for p, tgt in (symlinks or {}).items():
            fp = os.path.join(t, p); os.makedirs(os.path.dirname(fp), exist_ok=True); os.symlink(tgt, fp)
        return validate_dir(t)
if __name__ == "__main__":
    e = validate_dir(sys.argv[1] if len(sys.argv) > 1 else "")
    if e: print("omarchy-plugin-validate: " + e, file=sys.stderr); sys.exit(1)
