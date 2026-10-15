#!/usr/bin/env python3
"""Lifecycle / manifest / supply-chain rules (v3-fixes). Ids: USB-N* (manifest), USB-L* (entry-point lifecycle), USB-W11..W14 (supply chain).
Host facts verified against the shipped shell tree (functest/dell_env/omarchy-shell-ref.tar.gz, shell.qml + services/PluginRegistry.qml)
and against Quickshell 0.3.2 on the build box; see docs/V3_FIXES.md for the evidence per rule.
check(files, enabled=None) -> [dict(rule, severity, file, line, reason, hint)]. ENABLED / EXPERIMENTAL come from lifecycle_rules_enabled.json
(written by hancore/measure_lifecycle.py from design-split measurements)."""
import re, os, json
HERE = os.path.dirname(os.path.abspath(__file__))
KIND_KEY = {"bar-widget": "barWidget", "panel": "panel", "overlay": "overlay", "menu": "menu", "service": "service", "bar": "bar"}
SURFACE = ("panel", "overlay", "menu")
RULES = {
 "USB-N01": ("manifest", "declared kind has no matching entryPoints key (bar-widget -> barWidget; panel/overlay/menu/service/bar -> same name)"),
 "USB-N02": ("manifest", "manifest rejected by the shell registry: schemaVersion is not the number 1, or id/name/version/kinds/entryPoints missing, or kinds empty"),
 "USB-L01": ("lifecycle", "panel/overlay/menu entry does not define both open(payloadJson) and close() at its root"),
 "USB-L02": ("lifecycle", "entry root is ShellRoot (second shell root) or the plugin starts its own quickshell process"),
 "USB-L03": ("lifecycle", "`required property` named like a host-injected property (shell, manifest, omarchyPath, pluginRegistry, barWidgetRegistry, barConfig, service) on an entry root: the Loader cannot initialise it"),
 "USB-W11": ("remote-code-pinning", "`cargo install --git` without a 40-hex --rev"),
 "USB-W12": ("remote-code-pinning", "GitHub Actions `uses:` not pinned to a 40-hex commit SHA"),
 "USB-W13": ("privileged-system", "broad passwordless sudoers (NOPASSWD: ALL or a shell/interpreter)"),
 "USB-W14": ("privileged-system", "bundled native binary (ELF/PE/Mach-O magic) in the plugin tree"),
}
_f = os.path.join(HERE, "lifecycle_rules_enabled.json")
_cfg = json.load(open(_f)) if os.path.exists(_f) else {}
ENABLED = set(_cfg.get("enabled", RULES))
EXPERIMENTAL = set(RULES) - ENABLED
INJECTED = ("shell", "manifest", "omarchyPath", "pluginRegistry", "barWidgetRegistry", "barConfig", "service")
# qs.Ui roots that already provide open() AND close() (verified in shell/Ui/*.qml); KeyboardPanel / PopupCard only provide close()
UI_FULL = {"Panel"}
BASIC = {"Item", "Rectangle", "PanelWindow", "FloatingWindow", "QtObject", "Scope", "Column", "Row", "Window", "PopupWindow", "WlrLayershell", "Loader", "Repeater",
         "MouseArea", "FocusScope", "Canvas", "ShellRoot", "BarWidget", "KeyboardPanel", "PopupCard", "SpeedTestOverlay", "ColumnLayout", "RowLayout", "Variants", "LazyLoader"}

def _strip(c):
    """blank out comments and string contents, keeping offsets/newlines."""
    out = []; i = 0; n = len(c)
    while i < n:
        ch = c[i]
        if c.startswith("//", i):
            j = c.find("\n", i); j = n if j < 0 else j; out.append(" " * (j - i)); i = j
        elif c.startswith("/*", i):
            j = c.find("*/", i + 2); j = n if j < 0 else j + 2; out.append(re.sub(r"[^\n]", " ", c[i:j])); i = j
        elif ch in "\"'`":
            q = ch; j = i + 1
            while j < n and c[j] != q and not (c[j] == "\n" and q != "`"): j += 2 if c[j] == "\\" else 1
            j = min(j + 1, n); out.append(q + re.sub(r"[^\n]", " ", c[i + 1:j - 1]) + (q if j - 1 > i else "")); i = j
        else: out.append(ch); i += 1
    return "".join(out)
def root_info(c):
    """(root_type, {depth-1 function names}, {depth-1 property names with 'required'}), best effort."""
    s = _strip(c)
    m = re.search(r"(?m)^[ \t]*([A-Z][\w.]*)\s*\{", s)
    if not m: return None, set(), []
    fns = set(); req = []; d = 1; i = m.end(); line_start = i
    while i < len(s) and d:
        ch = s[i]
        if ch == "{": d += 1
        elif ch == "}": d -= 1
        elif ch == "\n":
            line_start = i + 1
            if d == 1:
                ln = s[line_start:s.find("\n", line_start) if s.find("\n", line_start) >= 0 else len(s)]
                mm = re.match(r"\s*function\s+(\w+)\s*\(", ln)
                if mm: fns.add(mm.group(1))
                mm = re.match(r"\s*required\s+property\s+[\w.<>]+\s+(\w+)", ln)
                if mm: req.append((mm.group(1), s.count("\n", 0, line_start) + 1))
        i += 1
    # same-line first statement (e.g. `Item { function open() {}`)
    return m.group(1), fns, req

def _manifest(files):
    try: return json.loads(files["manifest.json"])
    except Exception: return None
def _entry_files(man, files):
    if not isinstance(man, dict) or not isinstance(man.get("entryPoints"), dict): return {}
    return {k: v for k, v in man["entryPoints"].items() if isinstance(v, str) and v in files}
def _resolve_root(files, path, c, depth=0):
    """follow local-component roots: returns (fn_names, root_type)."""
    rt, fns, req = root_info(c)
    if rt and depth < 4 and rt not in BASIC and rt not in UI_FULL:
        cand = os.path.join(os.path.dirname(path), rt + ".qml").lstrip("./")
        if cand not in files: cand = next((q for q in files if q.endswith("/" + rt + ".qml") or q == rt + ".qml"), None)
        if cand:
            f2, rt2 = _resolve_root(files, cand, files[cand], depth + 1)
            return fns | f2, rt
    return fns, rt

def check(files, enabled=None):
    en = ENABLED if enabled is None else enabled
    out = []
    def add(rule, f, line, reason, hint="", sev="medium"):
        if rule in en: out.append(dict(rule=rule, category=RULES[rule][0], file=f, line=max(1, line or 1), reason=reason, hint=hint, severity=sev))
    man = _manifest(files)
    if isinstance(man, dict):
        mt = files["manifest.json"]
        kinds = man.get("kinds") if isinstance(man.get("kinds"), list) else []
        eps = man.get("entryPoints") if isinstance(man.get("entryPoints"), dict) else None
        # N02 registry validation (services/PluginRegistry.qml validateManifest)
        bad = []
        if man.get("schemaVersion") != 1 or isinstance(man.get("schemaVersion"), bool): bad.append("schemaVersion is not the number 1")
        for k in ("id", "name", "version", "kinds", "entryPoints"):
            if k not in man: bad.append(f"`{k}` missing")
        if "kinds" in man and not (isinstance(man["kinds"], list) and man["kinds"]): bad.append("`kinds` is not a non-empty array")
        if "entryPoints" in man and not isinstance(man["entryPoints"], dict): bad.append("`entryPoints` is not an object")
        if bad: add("USB-N02", "manifest.json", 1, "the shell registry rejects this manifest: " + "; ".join(bad), "use schemaVersion 1 and all required fields", "high")
        if eps is not None:
            for k in kinds:
                key = KIND_KEY.get(k)
                if key and not isinstance(eps.get(key), str):
                    ln = next((i for i, l in enumerate(mt.splitlines(), 1) if "entryPoints" in l), 1)
                    add("USB-N01", "manifest.json", ln, f"kind `{k}` is declared but `entryPoints` has no `{key}` key (the shell reads entryPoints.{key})", f"add \"{key}\": \"<File>.qml\" to entryPoints", "high")
        entries = _entry_files(man, files)
        for kind in SURFACE:
            if kind in kinds and kind in entries:
                p = entries[kind]; c = files[p]
                fns, rt = _resolve_root(files, p, c)
                if rt in UI_FULL and "Panel" == rt: continue
                miss = [f for f in ("open", "close") if f not in fns]
                # not a summoned surface: persistent HUD driven by its service (kinds has `service`, or the root reads `service`), or a root type we cannot resolve
                if "service" in kinds or re.search(r"\bservice\b\s*[:.]|property\s+\w+\s+service\b", _strip(c)): continue
                if rt not in BASIC: continue
                if miss and rt != "ShellRoot":
                    ln = next((i for i, l in enumerate(c.splitlines(), 1) if re.match(r"\s*[A-Z][\w.]*\s*\{", l)), 1)
                    add("USB-L01", p, ln, f"`{kind}` entry root `{rt}` defines no `{'` / `'.join(m + '()' for m in miss)}`; the shell calls open(payloadJson) to show and close() to hide the surface and silently skips a missing function", "define `function open(payloadJson)` and `function close()` (and a truthful `opened`)", "high")
        for k, p in entries.items():
            c = files[p]; rt, fns, req = root_info(c)
            if rt == "ShellRoot": add("USB-L02", p, 1 + len(c[:re.search(r"ShellRoot", c).start()].splitlines()) - 1 if re.search(r"ShellRoot", c) else 1, "entry root is `ShellRoot`: the host is already the Quickshell root, entry points must be hosted Items", "use Item (or the qs.Ui Panel/BarWidget base) as the root", "medium")
            for name, ln in req:
                if name in INJECTED: add("USB-L03", p, ln, f"`required property {name}` on the entry root: the host assigns `{name}` only after load, so the Loader fails with 'Required property {name} was not initialized'", f"declare `property var {name}: null`", "high")
    for p, c in files.items():
        if p.endswith(".qml") and re.search(r"(?:command\s*:|execDetached\()\s*\[\s*[\"']quickshell[\"']", c):
            ln = next(i for i, l in enumerate(c.splitlines(), 1) if re.search(r"[\"']quickshell[\"']", l))
            add("USB-L02", p, ln, "starts its own `quickshell` process instead of being hosted by the running shell", "plugins are hosted items; never launch a second shell", "medium")
        for i, l in enumerate(c.splitlines(), 1):
            if len(l) > 800: continue
            if re.search(r"\bcargo\s+install\b[^\n]*--git\b", l) and not re.search(r"--rev[ =]+[\"']?[0-9a-f]{40}\b", l) and not re.match(r"\s*(#|//|echo|printf)", l):
                add("USB-W11", p, i, "`cargo install --git` without a 40-hex `--rev`: builds whatever the branch holds today", "add --rev <full commit sha> (and --locked)", "medium")
            if p.endswith((".yml", ".yaml")) and (p.startswith(".github/workflows/") or "/.github/workflows/" in p):
                m = re.match(r"\s*-?\s*uses:\s*([\w./-]+)@([\w./-]+)", l)
                if m and not m.group(1).startswith("./") and not re.fullmatch(r"[0-9a-f]{40}", m.group(2)):
                    add("USB-W12", p, i, f"`uses: {m.group(1)}@{m.group(2)}` is not pinned to a 40-hex commit", "pin the action to a full commit SHA", "low")
            if re.search(r"\bNOPASSWD\s*:\s*(?:ALL\b|/(?:usr/)?(?:s?bin)/(?:ba|z|da)?sh\b|/(?:usr/)?bin/(?:python3?|perl|env|bash)\b|\*)", l) and not re.match(r"\s*(#|//)", l):
                add("USB-W13", p, i, "broad passwordless sudo rule (`NOPASSWD` for ALL or an interpreter)", "do not ship sudoers; use a fixed root-owned helper with one polkit action", "high")
    return out
def bundled_binaries(blobs):
    """USB-W14 needs raw bytes: blobs = {path: first bytes}; returns findings. Text-only rows cannot trigger it."""
    out = []
    for p, b in blobs.items():
        if b[:4] == b"\x7fELF" or b[:2] == b"MZ" or b[:4] in (b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe"):
            if "W14" in "".join(ENABLED) or "USB-W14" in ENABLED:
                out.append(dict(rule="USB-W14", category=RULES["USB-W14"][0], file=p, line=1, reason="bundled native binary", hint="build from source on install or declare the dependency", severity="low"))
    return out
if __name__ == "__main__":
    import sys; sys.path.insert(0, os.path.dirname(HERE)); import functest
    for f in check(functest.read_dir(sys.argv[1]), enabled=set(RULES)): print(f"[{f['rule']}] {f['file']}:{f['line']}: {f['reason']}")
