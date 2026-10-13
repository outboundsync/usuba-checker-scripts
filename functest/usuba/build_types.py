#!/usr/bin/env python3
"""Build usuba/types.json: the positive allowlist of QML types and their members, read from the real
Qt 6 / Quickshell qmltypes + qmldir files used by the functest runtime (mirrors the Dell: Qt 6.11, Quickshell /opt/qs611)
and from Omarchy 4.0.4's qs.Commons / qs.Ui QML. Re-run when the Dell's Qt/Quickshell/Omarchy changes."""
import json, os, re, glob, sys
QT = os.environ.get("FT_QT_QML", "/opt/qt/6.11.3/gcc_64/qml"); QS = os.environ.get("FT_QS_QML", "/opt/qs611/qml")
OM = os.environ.get("FT_OMARCHY", "/opt/ft/omarchy-4.0.4") + "/shell"
comps = {}       # C++ name -> {proto, props, signals, methods, exports, enums, singleton}
modules = {}     # module -> {types: {qmlName: cppName or "qml:<members>"}, imports: [...]}
def block_iter(txt):
    i = 0
    while True:
        m = re.compile(r"\n\s{4}Component \{").search(txt, i)
        if not m: return
        d, j = 0, m.end() - 1
        while j < len(txt):
            if txt[j] == "{": d += 1
            elif txt[j] == "}":
                d -= 1
                if d == 0: break
            j += 1
        yield txt[m.end():j]; i = j
def parse_qmltypes(path):
    t = open(path, errors="ignore").read()
    for b in block_iter(t):
        g = lambda k: (re.search(r'^\s{8}' + k + r':\s*"([^"]*)"', b, re.M) or [None, None])[1]
        name = g("name")
        if not name: continue
        c = comps.setdefault(name, dict(proto=g("prototype"), props=[], signals=[], methods=[], exports=[], enums=[], singleton=False,
                                         attached=g("attachedType")))
        c["props"] += re.findall(r'Property \{\s*name: "(\w+)"', b)
        c["signals"] += re.findall(r'Signal \{\s*name: "(\w+)"', b)
        c["methods"] += re.findall(r'Method \{\s*name: "(\w+)"', b)
        c["enums"] += re.findall(r'Enum \{\s*name: "(\w+)"', b)
        for vals in re.findall(r'values:\s*\[([^\]]*)\]', b): c["enums"] += re.findall(r'"(\w+)"', vals)
        c["singleton"] = c["singleton"] or "isSingleton: true" in b
        em = re.search(r'exports:\s*\[([^\]]*)\]', b)
        for e in re.findall(r'"([\w.]+)/(\w+) [\d.]+"', em.group(1) if em else ""):
            c["exports"].append(e); modules.setdefault(e[0], {"types": {}, "imports": []})["types"][e[1]] = name
def qml_members(path):
    s = re.sub(r"//[^\n]*", "", open(path, errors="ignore").read())
    m = set(re.findall(r"\bproperty\s+[\w.<>]+\s+(\w+)", s)) | set(re.findall(r"\bfunction\s+(\w+)", s)) | set(re.findall(r"\bsignal\s+(\w+)", s))
    m |= set(re.findall(r"\balias\s+(\w+)", s))
    rt = re.search(r"^\s*([A-Z][\w.]*)\s*\{", re.sub(r"^\s*(import|pragma)[^\n]*", "", s, flags=re.M), re.M)
    return sorted(m), (rt.group(1) if rt else None)
def parse_qmldir(d, mod):
    q = os.path.join(d, "qmldir")
    if not os.path.exists(q): return
    M = modules.setdefault(mod, {"types": {}, "imports": []})
    for line in open(q):
        w = line.split()
        if not w: continue
        if w[0] in ("import",) or (w[0] in ("optional", "default") and len(w) > 2 and w[1] == "import"):
            ws = [x for x in w if x not in ("auto", "optional", "default", "import") and not re.match(r"[\d.]+$", x)]
            if ws: M["imports"].append(ws[0])
        elif w[0] == "singleton" and len(w) >= 3 and w[-1].endswith(".qml"):
            mem, rt = qml_members(os.path.join(d, w[-1])); M["types"][w[1]] = {"qml": mem, "root": rt, "singleton": True}
        elif re.match(r"[A-Z]\w*$", w[0]) and w[-1].endswith(".qml") and len(w) >= 2:
            if os.path.exists(os.path.join(d, w[-1])):
                mem, rt = qml_members(os.path.join(d, w[-1])); M["types"].setdefault(w[0], {"qml": mem, "root": rt})
for root, mod_prefix in ((QT, ""), (QS, "")):
    for f in glob.glob(root + "/**/*.qmltypes", recursive=True): parse_qmltypes(f)
    for q in glob.glob(root + "/**/qmldir", recursive=True):
        d = os.path.dirname(q); mod = os.path.relpath(d, root).replace("/", ".")
        parse_qmldir(d, mod)
for sub, mod in (("Commons", "qs.Commons"), ("Ui", "qs.Ui")):
    parse_qmldir(os.path.join(OM, sub), mod)
    # singletons/types listed implicitly (no qmldir entry) still resolve inside the module dir
    for f in glob.glob(os.path.join(OM, sub, "*.qml")):
        n = os.path.basename(f)[:-4]
        if n not in modules.setdefault(mod, {"types": {}, "imports": []})["types"]:
            mem, rt = qml_members(f); modules[mod]["types"][n] = {"qml": mem, "root": rt}
# the `shell` object Omarchy injects into third-party plugins that declare `property var shell` (shell.qml pluginShellFor -> PluginShellApi)
shell_api, _ = qml_members(os.path.join(OM, "services", "PluginShellApi.qml"))
# service plugins also receive the shell root itself (shell.qml), e.g. shell.shellConfig used by built-in idle service
_root, _ = qml_members(os.path.join(OM, "shell.qml"))
shell_api = sorted(set(shell_api) | set(_root)) if isinstance(shell_api, list) else {**_root, **shell_api}
json.dump({"comps": comps, "modules": modules, "shell_api": shell_api, "source": {"qt": QT, "quickshell": QS, "omarchy": OM}},
          open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "types.json"), "w"), sort_keys=True)
print(len(comps), "components", len(modules), "modules", {m: len(modules[m]["types"]) for m in ("QtQuick", "Quickshell", "Quickshell.Io", "qs.Commons", "qs.Ui") if m in modules})
