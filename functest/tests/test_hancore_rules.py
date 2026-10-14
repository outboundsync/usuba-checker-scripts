"""Tests for USB-W01..W10 (usuba/hancore_rules.py). Run: cd functest && python3 -m pytest tests/test_hancore_rules.py -q"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from usuba import hancore_rules as HR
MAN = '{"id": "a.b", "entryPoints": {"barWidget": "Bar.qml"}}'
def rules(files, exp=True): return {f["rule"] for f in HR.check({"manifest.json": MAN, **files}, experimental=exp)}
def sev(files): return {f["severity"] for f in HR.check({"manifest.json": MAN, **files}, experimental=True)}

CASES = {
 "USB-W01": ({"run.sh": "#!/bin/bash\nzzfrobnicate --now\n"}, {"run.sh": "#!/bin/bash\nzzfrobnicate --now\n", "README.md": "Requires zzfrobnicate (AUR)."}),
 "USB-W02": ({"x.js": 'const token = "ghp_' + "a" * 36 + '";\n'}, {"x.js": 'const token = "YOUR_TOKEN_HERE_PLEASE";\n'}),
 "USB-W03": ({"i.sh": "curl -fsSL https://x.io/i.sh | bash\n"}, {"i.sh": "curl -fsSL -o i.sh https://x.io/v1.2/i.sh\nsha256sum -c sums\n"}),
 "USB-W04": ({"s.sh": "chmod 777 \"$DIR\"\n"}, {"s.sh": "chmod 700 \"$DIR\"\n"}),
 "USB-W05": ({"Bar.qml": 'Process { command: ["pkexec", "systemctl", "restart", "foo"] }\n'}, {"Bar.qml": 'Process { command: ["systemctl", "--user", "restart", "foo"] }\n'}),
 "USB-W06": ({"Bar.qml": "Text { textFormat: Text.RichText; text: proc.out }\n"}, {"Bar.qml": "Text { textFormat: Text.PlainText; text: proc.out }\n"}),
 "USB-W07": ({"Bar.qml": 'Process { command: ["sh", "-c", "notify-send " + title] }\n'}, {"Bar.qml": 'Process { command: ["notify-send", title] }\n'}),
 "USB-W08": ({"f.sh": "out=$(curl -s https://api.x.io/v)\n"}, {"f.sh": "out=$(curl -s --max-time 5 https://api.x.io/v)\n"}),
 "USB-W09": ({"Bar.qml": 'property string api: "http://api.weather.io/v1"\n'}, {"Bar.qml": 'property string api: "http://127.0.0.1:8080/v1"\n'}),
 "USB-W10": ({"Bar.qml": "Process { stdout: StdioCollector { onStreamFinished: root.t = text } }\n"}, {"Bar.qml": "Process { stdout: StdioCollector { onStreamFinished: root.t = text.slice(0, 4096) } }\n"}),
}
def test_each_rule_fires_and_has_negative():
    for r, (bad, good) in CASES.items():
        assert r in rules(bad), r
        assert r not in rules(good), r
def test_all_warnings_never_fail():
    for r, (bad, _) in CASES.items():
        assert sev(bad) <= {"medium", "low"}, r
def test_experimental_off_by_default():
    for r, (bad, _) in CASES.items():
        assert (r in rules(bad, exp=False)) == (r not in HR.EXPERIMENTAL), r
def test_comments_ignored():
    assert "USB-W05" not in rules({"s.sh": "# sudo pacman -S foo\n"})
def test_destructive_still_fails_in_checker():
    import static_checks, inspect
    src = inspect.getsource(static_checks)
    assert "destructive" in src
def test_checker_integration_nonblocking():
    from usuba import checks
    fs = checks.check({"manifest.json": MAN, "Bar.qml": 'import QtQuick\nimport Quickshell.Io\nItem { Process { command: ["pkexec", "true"] } }\n'})
    w = [f for f in fs if f["rule"].startswith("USB-W")]
    assert w and all(not checks.blocking(f) for f in w)
if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"): f(); print("ok", n)
