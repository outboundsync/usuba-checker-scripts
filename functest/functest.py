#!/usr/bin/env python3
"""Combined functional test = static checks + real-shell runtime. `python3 functest.py <plugin_dir>`"""
import json, os, sys, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import static_checks, runtime, dell_checks
from usuba import checks as usuba_checks

SKIP_DIRS = {".git", "node_modules", "tests", "test", "__pycache__", "preview", "stubs", "lint", ".github", "fixtures", "docs", "screenshots", "assets"}
def read_dir(d):
    files = {}
    for r, ds, fs in os.walk(d):
        ds[:] = [x for x in ds if x not in SKIP_DIRS]
        for f in fs:
            p = os.path.relpath(os.path.join(r, f), d)
            if os.path.getsize(os.path.join(r, f)) > 2_000_000: continue
            try: files[p] = open(os.path.join(r, f), encoding="utf-8").read()
            except Exception: pass
    return files

def categories(st_fails, rt):
    cats = sorted({c for c, _ in st_fails})
    for e in (rt or {}).get("errors", []):
        if e.startswith("DANGEROUS") or e.startswith("wrote outside"): cats.append("rt-dangerous-write")
        elif e.startswith("exec:") and "does not exist on the Dell" in e: cats.append("rt-missing-binary")
        elif e.startswith("exec:"): cats.append("rt-undefined-arg")
        elif e.startswith("renders undefined"): cats.append("rt-undefined-text")
        elif e.startswith("shell broke"): cats.append("rt-shell-broken")
        elif e.startswith("plugin reported"): cats.append("rt-plugin-warn")
        elif "outside the screen" in e or "item is not visible" in e: cats.append("rt-offscreen")
        elif "illegible" in e or "draws nothing visible" in e or "not visible on screen" in e: cats.append("rt-invisible")
        elif "is not a type" in e or "is not installed" in e or "module" in e.lower() and "not" in e: cats.append("rt-unresolved-type/import")
        elif re.search(r"(TypeError|ReferenceError|is not a function|is not defined|undefined)", e): cats.append("rt-js-error")
        elif re.search(r"(Expected token|Syntax|Unexpected token|Unexpected)", e): cats.append("rt-qml-syntax")
        elif re.search(r"(Cannot assign|Invalid property|Non-existent|Unable to assign|does not have a property|Invalid attached)", e): cats.append("rt-bad-property")
        elif "rejected" in e: cats.append("rt-manifest-rejected")
        elif "never registered" in e or "failed to load" in e or "load failed" in e: cats.append("rt-load-failed")
        elif "never instantiated" in e or "not instantiated" in e or "not created" in e or "not active" in e: cats.append("rt-not-instantiated")
        elif "zero size" in e: cats.append("rt-zero-size")
        else: cats.append("rt-other")
    return sorted(set(cats))

def test(files=None, src_dir=None, run_runtime=True):
    if src_dir: files = read_dir(src_dir)
    sf, sw = static_checks.check(files)
    df, dw = dell_checks.check(files, doc_deps=not os.environ.get("FT_STRICT_DEPS"))
    sf, sw = sf + df, sw + dw
    # Usuba Checker hardening (functest/STANDARD.md): errors and high-severity heuristics block, the rest are flags
    uf = usuba_checks.check(files)
    sf = sf + [("usuba-" + f["rule"], usuba_checks.fmt(f)) for f in uf if usuba_checks.blocking(f)]
    sw = sw + [("usuba-" + f["rule"], usuba_checks.fmt(f)) for f in uf if not usuba_checks.blocking(f)]
    rt = None
    man_ok = True
    try: m = json.loads(files.get("manifest.json", "")); man_ok = isinstance(m, dict) and "id" in m
    except Exception: man_ok = False
    if run_runtime and man_ok:
        rt = runtime.run(src_dir=src_dir) if src_dir else runtime.run(files=files)
        timing = ("never instantiated", "not instantiated", "not created", "not active", "IPC unreachable", "harness timeout",
                  "not visible on screen without fullscreen")   # pixel check can race the first frame under load
        if rt.get("errors") and all(any(t in e for t in timing) for e in rt["errors"]):
            rt2 = runtime.run(src_dir=src_dir) if src_dir else runtime.run(files=files)   # async-load timing retry
            rt2["retried"] = True
            if len(rt2.get("errors", [])) <= len(rt["errors"]): rt = rt2
    elif run_runtime: rt = {"pass": False, "errors": ["no valid manifest.json"]}
    if rt and isinstance(man_ok, bool) and man_ok:
        ep = (m.get("entryPoints") or {}).get("barWidget") if isinstance(m.get("entryPoints"), dict) else None
        src = files.get(ep or "", "")
        for e in list(rt.get("errors", [])):
            if ("zero size" in e or "draws nothing visible" in e) and re.search(r"^\s*(visible|implicitWidth|width|opacity)\s*:[^\n]*(\?|&&|\|\||>|<|===|!==)", src, re.M):
                rt["errors"].remove(e); rt.setdefault("soft", []).append(e + " (conditionally hidden by design)")
        rt["pass"] = not rt["errors"]
    ok = not sf and (rt is None or rt.get("pass"))
    return {"pass": ok, "static_fails": sf, "static_flags": sw, "runtime": rt, "categories": categories(sf, rt), "usuba": uf}

if __name__ == "__main__":
    r = test(src_dir=sys.argv[1])
    if "--reasons" in sys.argv:
        from usuba import rules
        print("PASS" if r["pass"] else "FAIL")
        for l in rules.explain(r["static_fails"], (r["runtime"] or {}).get("errors", [])): print("  " + l)
        for c, d in r["static_flags"]:
            if c.startswith("usuba-"): print("  warn " + d)
    else: print(json.dumps({k: v for k, v in r.items()}, indent=1)[:6000])
