"""Audit D10: one failing and one passing fixture for every static error-level rule that had none (ratchet: tests/rules_without_fixture.json).

Fixtures are tiny QML/JS/JSON snippets fed to the static Checker (``run_runtime=False``): nothing is executed. A rule "fires" when its id is in
the blocking static failures (category -> rule id through ``usuba.rules.rule_for``) or is an error-level Usuba finding. The four runtime rules need the
real Quickshell runtime and stay in the ratchet list.
"""
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("FT_OMARCHY", os.path.join(ROOT, "dell-ref", "omarchy-4.0.4"))
import functest  # noqa: E402
from usuba import rules  # noqa: E402

MANIFEST = '{"id":"a.b","name":"x","version":"1.0.0","entryPoints":{"barWidget":"W.qml"}}'


def fired(files):
    files = dict(files)
    files.setdefault("manifest.json", MANIFEST)
    r = functest.test(files=files, run_runtime=False)
    ids = {f["rule"] for f in r["usuba"] if f.get("severity") == "error"}
    ids.update(rules.rule_for(c) for c, _ in r["static_fails"])
    return ids


HDR = "import QtQuick\nimport Quickshell\nimport Quickshell.Io\n"
def W(body, imports=HDR):
    return {"W.qml": imports + "Item {\n  id: root\n  width: 20; height: 20\n  property int tick: 0\n  Timer { interval: 1000; running: true; repeat: true; onTriggered: root.tick += 1 }\n  Text { text: 'tick ' + root.tick }\n  MouseArea { anchors.fill: parent; onClicked: root.tick = 0 }\n" + body + "\n}\n"}
C = {}
C["USB-A01"] = (W("  Component.onCompleted: { Qt.clipboard.text = 'x' }"), W("  Component.onCompleted: { console.log('x') }"))
C["USB-A02"] = (W("  Process { id: p; command: ['true']; onFinished: console.log('x') }"), W("  Process { id: p; command: ['true']; onExited: console.log('x') }"))
C["USB-A04"] = (W("  Process { id: proc; command: ['true'] }\n  Component.onCompleted: proc.start()"), W("  Process { id: proc; command: ['true']; running: true }"))
C["USB-A05"] = (W("  Component.onCompleted: { const cp = require('child_process') }"), W("  Component.onCompleted: { const a = 1 }"))
C["USB-A06"] = (W("  Text { color: Color.accent2 }", HDR + "import qs.Commons\n"), W("  Text { color: Color.foreground }", HDR + "import qs.Commons\n"))
C["USB-A07"] = (W("  property var shell\n  Component.onCompleted: { console.log(shell.notamember) }"), W("  property var shell\n  Component.onCompleted: { console.log(root.tick) }"))
C["USB-B01"] = (W("  Process { command: ['sh','-c','playerctl-nonexistent-tool status | head -1']; running: true }"), W("  Process { command: ['sh','-c','echo hi | head -1']; running: true }"))
C["USB-B02"] = (W("  Process { command: ['setxkbmap','de']; running: true }"), W("  Process { command: ['true']; running: true }"))
C["USB-B03"] = (W("  Process { command: ['sh','-c','hyprctl background add x.png']; running: true }"), W("  Process { command: ['sh','-c','hyprctl monitors']; running: true }"))
C["USB-B04"] = (W("  Process { command: ['sh','-c','hyprctl keyword general:gaps_in 4; hyprctl reload']; running: true }"), W("  Process { command: ['sh','-c','hyprctl keyword general:gaps_in 4']; running: true }"))
C["USB-B05"] = (W("  Process { command: ['walker-not-installed-xyz']; running: true }"), W("  Process { command: ['true']; running: true }"))
C["USB-B06"] = (W("  Process { command: ['sh','-c','fcitx5-remote -l']; running: true }"), W("  Process { command: ['sh','-c','echo ok']; running: true }"))
C["USB-F01"] = (W("  Process { command: ['bash', Qt.resolvedUrl('bin/speed.sh')]; running: true }"), dict(W("  Process { command: ['bash', Qt.resolvedUrl('bin/speed.sh')]; running: true }"), **{"bin/speed.sh": "#!/bin/sh\necho 1\n"}))
C["USB-H05"] = ({"W.qml": HDR + "Item { id: root; Text { text: 'x' } }\n"}, W(""))
C["USB-H06"] = (W("  ListView { model: ['Item 1', 'Item 2', 'Item 3'] }"), W("  ListView { model: root.items }\n  property var items: []"))
C["USB-J01"] = (W("  Component.onCompleted: { try { const w = shell.wm.windows } catch (e) {} }"), W("  Component.onCompleted: { const w = 1 }"))
C["USB-J02"] = (W("  property var settings: ({})\n  Process { command: ['echo', root.settings.mode]; running: true }"), W("  Process { command: ['echo', 'mode']; running: true }"))
C["USB-J03"] = (W("  Component.onCompleted: { var u = Qt.resolvedUrl('~/.config/x') }"), W("  Component.onCompleted: { var u = Qt.resolvedUrl('x.qml') }"))
C["USB-J04"] = (W("  Process { command: ['bash', Qt.resolvedUrl('x.sh')]; running: true }"), W("  Process { command: ['bash', '/usr/bin/true']; running: true }"))
GOODM = '{"id":"a.b","name":"x","version":"1.0.0","entryPoints":{"barWidget":"W.qml"}}'
C["USB-M01"] = (dict(W(""), **{"manifest.json": '{"id": "a.b",}'}), W(""))
C["USB-M02"] = ({"manifest.json": '{"id":"a.b","name":"x","version":"1.0.0","entryPoints":{"barWidget":"main.js"}}', "main.js": "var a = 1;"}, W(""))
C["USB-M03"] = ({"manifest.json": '{"id":"a.b","name":"x","version":"1.0.0"}', "tablet.py": "print(1)"}, W(""))
C["USB-M04"] = ({"W.qml": HDR + "import QtQuick.Controls\nApplicationWindow { visible: true; Text { text: 'x' } }\n"}, W(""))
C["USB-Q01"] = (W("  Item { layer.enabled: true; layer.effect: DropShadow { radius: 4 } }", "import QtQuick\n"), W("  Item { }", "import QtQuick\n"))
C["USB-Q02"] = (W("  Text { text: 'x' }", HDR + "import qs.Services\n"), W("  Text { text: 'x' }", HDR))
C["USB-Q03"] = (W("  Text { text: 'x' }", HDR + "import QtGraphicalEffects 1.15\n"), W("  Text { text: 'x' }", HDR))
C["USB-Q04"] = (W("  Component.onCompleted: { Timer { } }"), W("  Timer { interval: 1000 }"))
C["USB-Q05"] = (W("  QtObject { Timer { interval: 1000 } }"), W("  Timer { interval: 1000 }"))
C["USB-S03"] = (W("  Process { command: ['sh','-c','rm -rf $HOME']; running: true }"), W("  Process { command: ['sh','-c','echo ok']; running: true }"))
C["USB-A03"] = (W("  Component.onCompleted: { var t = new Timer() }"), W("  Timer { id: tt; interval: 5 }"))
C["USB-J06"] = (dict(W("  Loader { id: ld; source: 'Child.qml'; onLoaded: item.vaultPath = '/x' }"), **{"Child.qml": "import QtQuick\nItem {\n  property string vaultPath: ''\n  Component.onCompleted: { console.log(vaultPath) }\n}\n"}),
                dict(W("  Loader { id: ld; source: 'Child.qml'; onLoaded: item.vaultPath = '/x' }"), **{"Child.qml": "import QtQuick\nItem {\n  property string vaultPath: ''\n  onVaultPathChanged: console.log(vaultPath)\n}\n"}))


@pytest.mark.parametrize("rule", sorted(C))
def test_rule_fires_on_bad_and_not_on_good(rule):
    bad, good = C[rule]
    assert rule in fired(bad), f"{rule} did not fire on its failing fixture"
    assert rule not in fired(good), f"{rule} fired on its passing fixture"


def _task(prompt, task="build_plugin"):
    return {"task": task, "messages": [{"role": "system", "content": ""}, {"role": "user", "content": prompt}]}


def test_T01_manifest_only_answer_has_no_code():
    import rescore
    out = rescore.task_findings(_task("Write a complete Omarchy plugin"), {"manifest.json": MANIFEST})
    assert any(f[0] == "usuba-USB-T01" for f in out)
    code = "\n".join(f"Item {{ id: i{n} }}" for n in range(6))
    assert not any(f[0] == "usuba-USB-T01" for f in rescore.task_findings(_task("Write a plugin"), {"manifest.json": MANIFEST, "W.qml": code}))


def test_T02_requested_chunk_missing_or_stub():
    import rescore
    h = _task("Implement `HomeContent.qml` in full", "chunk_component")
    assert any(f[0] == "usuba-USB-T02" for f in rescore.task_findings(h, {"manifest.json": MANIFEST}))
    code = "\n".join(f"Item {{ id: i{n} }}" for n in range(6))
    assert not any(f[0] == "usuba-USB-T02" for f in rescore.task_findings(h, {"HomeContent.qml": code}))


def test_T03_leaked_reasoning_before_first_file():
    import rescore
    code = "\n".join(f"Item {{ id: i{n} }}" for n in range(6))
    files = {"W.qml": code}
    assert any(f[0] == "usuba-USB-T03" for f in rescore.task_findings(_task("Write a plugin"), files, output="Wait, actually the Loader...\n### W.qml\n"))
    assert not any(f[0] == "usuba-USB-T03" for f in rescore.task_findings(_task("Write a plugin"), files, output="Here are the files.\n### W.qml\n"))
