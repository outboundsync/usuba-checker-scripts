#!/usr/bin/env python3
"""Single source of truth for the Usuba Standard rule ids. STANDARD.md is generated from this table
(`python3 -m usuba.rules > STANDARD.md` from functest/), and every checker failure carries one of these ids."""
VERSION = "0.2"
TARGET = "Omarchy 4.0.4-1 (shell tree byte-identical to basecamp/omarchy@c668141), Quickshell + Qt 6.11 as installed on the reference Dell"
# id: (title, level, rationale, bad example, fix hint, implemented-by)
RULES = {
 # ---- task contract
 "USB-T01": ("Answer contains plugin code", "error", "A manifest alone (or an empty answer) installs nothing that runs; the old grader passed manifest-only answers on chunk tasks because the upstream tree supplied the code.",
             "### manifest.json only, for \"Write a complete Omarchy plugin ...\"", "return the QML entry point(s) the manifest names, in full", "rescore.task_findings"),
 "USB-T02": ("Requested file is delivered", "error", "When a task asks for a specific file, the answer must contain that file with a real implementation.",
             "\"Implement `HomeContent.qml` in full\" -> answer contains only manifest.json", "return the complete requested file", "rescore.task_findings"),
 # ---- manifest
 "USB-T03": ("Answer is files, not leaked reasoning", "error", "Long prose or self-correction ('Wait', 'Actually') before the first file means the output is a draft, not a deliverable; extraction is unreliable.", "Wait, actually the Loader... ### Panel.qml", "return only `### path` headings with fenced code", "rescore.py"),
 "USB-M01": ("manifest.json is valid JSON with an id", "error", "Omarchy refuses to register a plugin it cannot parse.", "trailing comma in manifest.json", "fix the JSON", "static_checks"),
 "USB-M02": ("Entry points are QML files", "error", "Quickshell loads QML only; a .js/.py entry point never loads.", "\"entryPoints\": {\"barWidget\": \"main.js\"}", "point entryPoints at .qml files", "static_checks"),
 "USB-M03": ("Plugin ships QML", "error", "A plugin with no QML has nothing for the shell to instantiate.", "manifest + tablet.py only", "add the QML entry points", "static_checks"),
 "USB-M04": ("Entry root is a shell surface", "error", "ApplicationWindow/Window roots open a desktop app window instead of a bar widget/panel/overlay.", "ApplicationWindow { ... } as barWidget", "use Item / BarWidget / Panel (qs.Ui) as the root", "static_checks"),
 "USB-M05": ("Namespaced, non-reserved id", "error", "Third-party plugins must use a namespaced id outside omarchy.*.", "\"id\": \"time-machine\"", "use e.g. \"jankeesvw.time-machine\"", "rescore (fix_manifest)"),
 # ---- QML types and imports
 "USB-Q01": ("Every QML type resolves (positive allowlist)", "error", "A type that no imported module provides makes the component fail to load. The allowlist is built from the real Qt 6 / Quickshell qmltypes and Omarchy qs.Commons/qs.Ui QML (usuba/types.json), plus the plugin's own QML files, qmldir entries and inline components.",
             "layer.effect: DropShadow { ... } with only `import QtQuick`; `Process { }` without `import Quickshell.Io`", "add the import that provides the type, or use a type that exists", "usuba/checks.py"),
 "USB-Q02": ("Imports exist", "error", "Importing a module that does not exist (or an Omarchy module other than qs.Commons/qs.Ui) breaks loading.", "import qs.Services", "import only Qt 6, Quickshell, qs.Commons, qs.Ui or shipped files", "static_checks"),
 "USB-Q03": ("No Qt 5 APIs", "error", "Omarchy runs Qt 6; Qt 5 modules are absent.", "import QtGraphicalEffects 1.15", "use Qt5Compat.GraphicalEffects or QtQuick.Effects", "static_checks"),
 "USB-Q04": ("Valid QML structure", "error", "QML objects cannot be declared inside JavaScript blocks.", "Component.onCompleted: { Timer { } }", "declare objects in QML, start them from JS", "static_checks"),
 # ---- APIs
 "USB-Q05": ("QtObject does not host child objects", "error", "QtObject has no default property, so Timer/Process/FileView declared inside it is a load error. From expert review (UC-QML-04).", "QtObject { Timer { interval: 1000 } }", "use an Item root or `property Timer t: Timer {}`", "usuba/checks.py"),
 "USB-A01": ("Only real APIs are called", "error", "Invented JS APIs throw at runtime, usually on a click path the smoke test never exercises. Members of `Qt.*` and `Quickshell.*` are checked against the real objects; calls on capitalised names must hit a singleton, JS import or id in scope. A small denylist of observed hallucinations backs this up.",
             "Quickshell.exec([...]).then(...); Qt.clipboard.text = s; Service.call(\"x\", \"y\")", "use Process / Quickshell.execDetached / omarchy-shell IPC / wl-copy", "usuba/checks.py"),
 "USB-A02": ("Signal handlers name real signals", "error", "A handler for a signal the type does not have never fires (or fails to load). Signals come from the type's qmltypes/QML definition plus its prototype chain.",
             "Process { onFinished: ... }  (Process has exited/started)", "use the type's real signal, e.g. onExited, or StdioCollector.onStreamFinished", "usuba/checks.py"),
 "USB-A08": ("Read-only bar facade properties are not assigned", "medium (warning)", "Warning only: 4 Dell-verified working plugins do this inside guarded code. Third-party plugins receive the read-only PluginBarApi facade; assigning a readonly member throws and aborts the function (e.g. close() leaves a keyboard grab). From expert review (UC-QML-01).", "bar.centerHoverRevealSuppressed = true", "bar.setCenterHoverRevealSuppressed(true)", "usuba/checks.py"),
 "USB-A03": ("QML types are not constructed with `new`", "error", "`new SequentialAnimation()` is not valid QML JavaScript.", "var a = new NumberAnimation()", "declare the object in QML with an id", "usuba/checks.py"),
 "USB-A04": ("Methods called on ids exist", "error", "Calling a method the object's type lacks throws a TypeError.", "proc.start()  // Process has no start()", "use the real method/property (running = true)", "usuba/checks.py"),
 "USB-A05": ("No Node/browser/C++ idioms in QML JS", "error", "require(), fetch(), document.*, QProcess etc. do not exist in Quickshell.", "const cp = require('child_process')", "use Process / XMLHttpRequest", "static_checks"),
 "USB-A06": ("qs.Commons singleton members exist", "error", "Color/Style/Util/Border members that the real singleton lacks are undefined.", "Color.accent2", "use a member that exists in shell/Commons", "dell_checks"),
 # ---- binaries and commands
 "USB-A07": ("Only real `shell` members are used", "error", "Omarchy injects a fixed shell object (PluginShellApi / shell.qml root); any other member is always undefined.", "shell.system.exec(...)", "use members listed in the Omarchy 4.0.4 PluginShellApi", "usuba/checks.py"),
 "USB-B01": ("Binaries in shell strings exist on the Dell", "error", "`sh -c`/`bash -c` strings, os.system strings and shipped shell scripts are parsed; every command word must be on the Dell's PATH (dell_env/system_bins.txt + omarchy_bins.txt), shipped, or documented as a dependency.",
             "[\"sh\", \"-c\", \"playerctl status | head -1\"]", "use an installed tool, ship a script, or document the dependency in README.md", "usuba/checks.py"),
 "USB-B02": ("No X11-only tools", "error", "Omarchy is a Wayland/Hyprland session; xinput, setxkbmap, xdotool, onboard, xclip, xrandr ... do nothing or are missing.", "subprocess.run([\"setxkbmap\", \"de\"])", "use hyprctl / wtype / wl-copy / a Wayland OSK", "usuba/checks.py"),
 "USB-B03": ("hyprctl / hyprsunset invocations are valid", "error", "Invented subcommands fail silently.", "hyprctl background add x.png; hyprsunset enable", "use real hyprctl commands; hyprsunset -t 4500 / hyprctl hyprsunset temperature 4500", "usuba/checks.py"),
 "USB-B04": ("No hyprctl reload after hyprctl keyword", "error", "`hyprctl reload` re-reads hyprland.conf and discards the runtime keywords just applied.", "hyprctl keyword general:gaps_in 4; hyprctl reload", "drop the reload", "usuba/checks.py"),
 "USB-B05": ("argv[0] exists on the Dell", "error", "A Process whose program is not installed never starts.", "command: [\"walker\"]", "use an installed program or ship/document it", "dell_checks"),
 # ---- files
 "USB-B06": ("CLI flags are real", "error", "Invented flags make the tool print usage and exit, so the feature silently does nothing.", "fcitx5-remote -l", "use flags from the tool's real getopt/--help on the Dell", "usuba/checks.py"),
 "USB-F01": ("Referenced helper scripts are shipped", "error", "A command that runs bin/foo.sh or scripts/x.py the plugin does not contain fails at click time.", "command: [\"bash\", Qt.resolvedUrl(\"bin/speed.sh\")] with no bin/speed.sh", "ship the script or inline the command", "usuba/checks.py"),
 # ---- JS correctness
 "USB-J01": ("No undeclared identifiers", "error", "Assigning or dereferencing a name that is never declared is a ReferenceError; wrapping it in try/catch only hides that the feature shows nothing.",
             "try { const w = shell.wm.windows } catch (e) {}", "declare the property and fill it from a real API", "usuba/checks.py"),
 "USB-J03": ("No Qt.resolvedUrl(\"~\")", "error", "resolvedUrl resolves relative to the QML file and never expands ~.", "Qt.resolvedUrl(\"~/.config/x\")", "use Quickshell.env(\"HOME\") or StandardPaths", "usuba/checks.py"),
 "USB-J04": ("argv paths are local paths, not URLs", "error", "Qt.resolvedUrl returns file:///...; passed to a program as a path it does not exist.", "command: [\"bash\", Qt.resolvedUrl(\"x.sh\")]", "strip the file:// scheme (e.g. .toString().replace(/^file:\\/\\//, \"\"))", "usuba/checks.py"),
 "USB-J06": ("Loader-passed properties are not read only in onCompleted", "error", "Properties set on Loader.item after load arrive after Component.onCompleted, so code that reads them only there always sees defaults.", "onLoaded: item.vaultPath = p  // child reads vaultPath only in onCompleted", "use setSource(url, {props}) or react in on<Prop>Changed", "usuba/checks.py"),
 "USB-J02": ("Commands never receive undefined", "error", "argv built from bar.<x>/settings.<x> that do not exist passes the string 'undefined'.", "command: [\"x\", settings.mode] with no `mode` default", "declare manifest defaults / use real PluginBarApi members", "dell_checks"),
 # ---- safety
 "USB-S01": ("Writes outside the plugin dir are flagged", "warn (high: protected config/system paths; medium: other paths outside plugin data dirs)", "Changing Hyprland/Omarchy config, /etc, /usr or shell rc files can surprise the user or break the session, but some plugins legitimately do it (e.g. a theme or keybind tool) - so it is a warning the reviewer must read, not a failure.", "echo ... >> ~/.config/hypr/hyprland.conf", "prefer hyprctl keyword / omarchy-shell IPC; if a write is the point of the plugin, say so in the README", "static_checks.py / runtime.py"),
 "USB-S02": ("Privileged or remote-exec commands are flagged", "warn (high)", "sudo/pkexec need a password prompt (a bar click just fails) and curl|sh runs unreviewed code; both are legitimate in installers, so they warn rather than fail.", "[\"pkexec\", \"systemctl\", ...]", "do not escalate from the shell; document manual steps or use a polkit-free path", "static_checks.py"),
 "USB-S03": ("No clearly destructive commands", "error", "rm -rf of $HOME, ~ or / destroys user data; this is the only safety case that stays a hard fail.", "rm -rf $HOME/", "never delete outside the plugin's own data dir", "static_checks.py / runtime.py"),
 # ---- HANCORE-derived warnings (usuba/hancore_rules.py; never fail)
 "USB-W01": ("Programs the plugin runs are documented dependencies", "warn (low; EXPERIMENTAL, off by default)", "Runs a program that a stock Omarchy install lacks and the README/manifest/PKGBUILD never mention; HANCORE's most common finding family (install-deps-packaging). Measured against HANCORE findings on 1375 non-holdout plugins: precision 0.45, recall 0.34 (base rate 0.33).", "command: [\"playerctl\", \"status\"] with no README mention", "list every external program (with its pacman/AUR package) and probe `command -v` before use", "usuba/hancore_rules.py"),
 "USB-W02": ("No hardcoded secrets or tokens", "warn (medium; on by default)", "Known token formats (ghp_, github_pat_, sk-, AKIA, xox*, AIza, private keys) or long literals assigned to key/token/secret/password names leak credentials to every user. Measured against HANCORE findings on 1375 non-holdout plugins: precision 0.50, recall 0.01 (base rate 0.27).", "const apiKey = \"sk-proj-...\"", "read secrets from the keyring (secret-tool) or a 0600 config outside the plugin", "usuba/hancore_rules.py"),
 "USB-W03": ("Remote code is pinned", "warn (medium; EXPERIMENTAL, off by default)", "curl|sh, git clone without a pinned SHA/tag, pip install git+URL without @ref, raw.githubusercontent main/master, releases/latest and unversioned npx run code that can change after review. Measured against HANCORE findings on 1375 non-holdout plugins: precision 0.45, recall 0.05 (base rate 0.19).", "curl -fsSL https://x/install.sh | bash", "pin to a full commit SHA or versioned release and verify a checksum", "usuba/hancore_rules.py"),
 "USB-W04": ("File operations are safe", "warn (medium; EXPERIMENTAL, off by default)", "World-writable chmod, forced symlinks, predictable /tmp paths and rm -rf on an unchecked variable allow symlink/TOCTOU attacks or data loss. (rm -rf of $HOME/~// itself is USB-S03, a fail.) Measured against HANCORE findings on 1375 non-holdout plugins: precision 0.40, recall 0.15 (base rate 0.33).", "echo $x > /tmp/state.json", "use mktemp or $XDG_RUNTIME_DIR, 0600/0700 modes, refuse symlinks, validate variables before rm -rf", "usuba/hancore_rules.py"),
 "USB-W05": ("Privileged actions are flagged", "warn (medium; on by default)", "sudo/pkexec/doas/run0, system-level systemctl, writes to /etc, /usr, /boot or /opt, and setuid modes; HANCORE asks for these to be removed or documented as manual steps. Measured against HANCORE findings on 1375 non-holdout plugins: precision 0.59, recall 0.35 (base rate 0.23).", "[\"pkexec\", \"tee\", \"/etc/foo.conf\"]", "stay unprivileged; document manual root steps in the README", "usuba/hancore_rules.py"),
 "USB-W06": ("Rich text is not bound to untrusted data", "warn (medium; EXPERIMENTAL, off by default)", "Text.RichText/StyledText/MarkdownText render links and images, so text from commands, files, the network or other apps can inject markup. Measured against HANCORE findings on 1375 non-holdout plugins: precision 0.27, recall 0.07 (base rate 0.18).", "textFormat: Text.RichText; text: notif.body", "use textFormat: Text.PlainText for non-literal text, or escape it", "usuba/hancore_rules.py"),
 "USB-W07": ("No interpolation into shell or Lua command strings", "warn (medium; EXPERIMENTAL, off by default)", "Concatenating or templating values into sh -c, eval, os.system/shell=True or hyprctl dispatch strings is command injection when the value comes from data. Measured against HANCORE findings on 1375 non-holdout plugins: precision 0.20, recall 0.14 (base rate 0.12).", "[\"sh\", \"-c\", \"notify-send \" + title]", "pass values as separate argv elements, or quote them", "usuba/hancore_rules.py"),
 "USB-W08": ("Network calls and processes have timeouts", "warn (low; EXPERIMENTAL, off by default)", "curl/wget without --max-time, requests/urlopen without timeout, and XMLHttpRequest without xhr.timeout can hang the widget forever. Measured against HANCORE findings on 1375 non-holdout plugins: precision 0.28, recall 0.11 (base rate 0.21).", "curl -s https://api/x", "add --max-time / timeout= / xhr.timeout, or wrap in `timeout 10`", "usuba/hancore_rules.py"),
 "USB-W09": ("Remote URLs use https", "warn (medium; EXPERIMENTAL, off by default)", "Plain http:// to a public host sends data without TLS (loopback and LAN addresses are exempt). Measured against HANCORE findings on 1375 non-holdout plugins: precision 0.25, recall 0.03 (base rate 0.19).", "http://api.example.org/v1", "use https://", "usuba/hancore_rules.py"),
 "USB-W10": ("Input is bounded", "warn (low; EXPERIMENTAL, off by default)", "StdioCollector/FileView/SplitParser output read with no size cap anywhere in the file can exhaust memory on huge output. Measured against HANCORE findings on 1375 non-holdout plugins: precision 0.38, recall 0.30 (base rate 0.40).", "FileView { path: log } with no cap", "cap the bytes read (head -c N, slice) before parsing", "usuba/hancore_rules.py"),
 # ---- heuristics (graded)
 "USB-H01": ("Real data, not simulated", "high/medium", "Code that says its data is simulated/mock/fake is a stub. High (blocking) when the wording is explicit or the plugin has no data source at all; medium otherwise.",
             "// Safe simulation: avoids calling external binaries\nstatus = \"Up to date\"", "read the real source (Process, FileView, Quickshell service)", "usuba/checks.py"),
 "USB-H02": ("No hardcoded readings shown as live data", "high/medium", "A literal like \"22°C\" or \"45%\" in a Text is a placeholder. High when the plugin has no IO at all.", "text: \"☀️ 22°C\"", "bind the text to a property filled from a real source", "usuba/checks.py"),
 "USB-H03": ("Handlers do something besides console.log", "high/low", "A plugin whose only side effects are console.log calls is a stub. High when there is no IO anywhere and >=3 logs; low for noisy logging.", "onClicked: console.log(\"toggled\")", "make each handler perform its action", "usuba/checks.py"),
 "USB-H04": ("No demo click handlers", "high", "A click handler whose only action is reporting the click (notify-send \"Clicked\", console.log) is a placeholder.", "onClicked: execDetached([\"notify-send\", \"Clicked at\"])", "make the click do what the plugin is for", "usuba/checks.py"),
 "USB-H05": ("Not a placeholder UI", "error", "All UI handlers empty/no-op, handlers calling empty functions, or a trivial plugin with no IO/data/interaction.", "onClicked: {}", "implement the behaviour", "static_checks"),
 "USB-H06": ("No placeholder data patterns", "error", "Lorem ipsum, Item 1/2/3, John Doe, random numbers presented as metrics.", "model: [\"Item 1\", \"Item 2\"]", "use real data", "static_checks"),
 # ---- runtime (real Quickshell on a headless compositor with the Dell's Omarchy tree)
 "USB-H07": ("No placeholder endpoints or credentials", "high", "example.com URLs or YOUR_API_KEY ship a plugin that can never reach real data.", "url: \"https://api.example.com/v1\"", "read endpoints/keys from settings or real config", "usuba/checks.py"),
 "USB-R01": ("Loads and registers in the real shell", "error", "The plugin must load, register and instantiate every entry point without QML errors.", "\"Foo is not a type\", \"failed to load\"", "fix the reported QML error", "runtime"),
 "USB-R02": ("No runtime JS/QML errors", "error", "TypeError/ReferenceError/binding errors during startup and the interaction probe.", "TypeError: Cannot read property 'x' of undefined", "guard the value or use the real API", "runtime"),
 "USB-R03": ("Visible, legible, on-screen", "error", "Bar widgets/panels must draw something visible, inside the screen, with legible contrast and non-zero size.", "zero-size bar widget", "give the widget implicit size and theme colours", "runtime"),
 "USB-R04": ("Runtime commands are valid", "error", "Processes run during the probe must exist on the Dell and receive defined arguments; no writes outside the plugin's area.", "exec: walker does not exist on the Dell", "use installed programs and defined args", "runtime"),
}
STATIC_CAT = {"manifest": "USB-M01", "entry-not-qml": "USB-M02", "no-qml": "USB-M03", "not-shell-surface": "USB-M04", "fix-id-not-namespaced": "USB-M05",
              "bad-import": "USB-Q02", "qt5-api": "USB-Q03", "qml-syntax": "USB-Q04", "fake-api": "USB-A05", "singleton-unknown": "USB-A06",
              "exec-unknown-binary": "USB-B05", "exec-undefined-arg": "USB-J02", "dangerous-write": "USB-S01", "dangerous-cmd": "USB-S02", "destructive-cmd": "USB-S03",
              "placeholder-ui": "USB-H05", "fake-data": "USB-H06"}
RT_CAT = {"rt-load-failed": "USB-R01", "rt-unresolved-type/import": "USB-R01", "rt-not-instantiated": "USB-R01", "rt-manifest-rejected": "USB-R01",
          "rt-qml-syntax": "USB-R01", "rt-shell-broken": "USB-R01", "rt-js-error": "USB-R02", "rt-bad-property": "USB-R02", "rt-plugin-warn": "USB-R02",
          "rt-other": "USB-R02", "rt-undefined-text": "USB-R02", "rt-invisible": "USB-R03", "rt-offscreen": "USB-R03", "rt-zero-size": "USB-R03",
          "rt-missing-binary": "USB-R04", "rt-undefined-arg": "USB-R04", "rt-dangerous-write": "USB-S01", "rt-destructive": "USB-S03"}
def rule_for(cat):
    if cat.startswith("usuba-"): return cat[6:]
    return STATIC_CAT.get(cat) or RT_CAT.get(cat)
def reason(cat, detail):
    rid = rule_for(cat)
    if not rid: return detail
    if detail.startswith("[" + rid): return detail
    return f"[{rid}] {detail}. Fix: {RULES[rid][4]}"

def runtime_rule(e):
    import functest
    cats = functest.categories([], {"errors": [e]})
    return RT_CAT.get(cats[0]) if cats else "USB-R02"
def explain(static_fails, runtime_errors=()):
    """Human-readable checker output: one line per failure, '[RULE] reason. Fix: hint'."""
    out = [reason(c, d) for c, d in static_fails]
    for e in runtime_errors or []:
        rid = runtime_rule(e) or "USB-R02"
        out.append(f"[{rid}] runtime: {e}. Fix: {RULES[rid][4]}")
    return out

def markdown():
    L = [f"# Usuba Standard v{VERSION}: what a working Omarchy plugin is", "",
         f"Target: {TARGET}.", "",
         "The Usuba Checker (functest/) enforces this standard: static checks (static_checks.py, dell_checks.py, usuba/checks.py), "
         "task-contract checks (rescore.py) and a real-shell runtime probe (runtime.py). Every failure the checker emits starts with a rule id "
         "from this document and ends with a `Fix:` hint.", "",
         "Levels: **error** always fails. **high** is a heuristic finding that fails (it is reported as `heuristic/high` so a human can overrule it). "
         "**medium**/**low** heuristics are warnings only.", "",
         "The type and member allowlists (USB-Q01, USB-A01, USB-A02, USB-A04) are generated by `usuba/build_types.py` from the qmltypes/qmldir files of "
         "the Qt 6.11 and Quickshell builds the runtime uses and from Omarchy 4.0.4's shell/Commons and shell/Ui, so they move with the Dell rather than "
         "with a hand-kept denylist.", ""]
    groups = [("T", "Task contract"), ("M", "Manifest"), ("Q", "QML types and imports"), ("A", "APIs"), ("B", "Binaries and commands"),
              ("F", "Shipped files"), ("J", "JavaScript correctness"), ("S", "Safety"), ("W", "Review warnings (from HANCORE findings)"), ("H", "Heuristics (graded)"), ("R", "Runtime")]
    for g, title in groups:
        L += [f"## {title}", ""]
        for rid, (t, lvl, why, ex, fix, by) in RULES.items():
            if rid[4] != g: continue
            L += [f"### {rid}: {t}", f"- Level: {lvl}", f"- Rationale: {why}", f"- Failing example: `{ex}`" if "\n" not in ex else "- Failing example:\n\n```\n" + ex + "\n```",
                  f"- Fix: {fix}", f"- Checked by: {by}", ""]
    L += ["## Changelog", "", "- v0.1 (2026-10-13): first public version. Adds USB-T01/T02, Q01, A01-A04, B01-B04, F01, J01, H01-H04 on top of the 4.0.4 functest "
          "(which scored 90/90 against the Dell answer key) after a fixer-loop experiment showed the old grader was gameable (13 passes, 4 real).",
          "- v0.2 (2026-10-13): adds USB-W01-W10, warnings derived from 12,989 HANCORE marketplace review findings. A rule is on by default only if its plugin-level precision against HANCORE is >= 0.5 and at least 0.10 above the category base rate (hancore/rule_metrics.json; holdout plugins excluded). Only W02 and W05 met that bar; the rest are experimental (run with experimental=True / --experimental). None of them fail a plugin; USB-S03 is still the only hard-fail safety rule."]
    return "\n".join(L) + "\n"
if __name__ == "__main__": print(markdown(), end="")
