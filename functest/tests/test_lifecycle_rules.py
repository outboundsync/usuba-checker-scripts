"""Tests for usuba/lifecycle_rules.py (v3-fixes). Run: cd functest && python3 -m pytest tests/test_lifecycle_rules.py (or python3 tests/test_lifecycle_rules.py)"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from usuba import lifecycle_rules as L
ALL = set(L.RULES)
def man(**k): return json.dumps(dict(dict(schemaVersion=1, id="ex.p", name="P", version="1.0.0"), **k))
OK = "import QtQuick\nItem {\n  property bool opened: false\n  function open(payloadJson) { opened = true }\n  function close() { opened = false }\n}\n"
def rules(files): return sorted(f["rule"] for f in L.check(files, ALL))
def test_overlay_toggle_only_flagged():
    f = {"manifest.json": man(kinds=["overlay"], entryPoints={"overlay": "O.qml"}), "O.qml": "import QtQuick\nItem {\n  function toggle() {}\n}\n"}
    assert rules(f) == ["USB-L01"]
def test_overlay_open_close_clean():
    assert rules({"manifest.json": man(kinds=["overlay"], entryPoints={"overlay": "O.qml"}), "O.qml": OK}) == []
def test_open_without_close_flagged():
    f = {"manifest.json": man(kinds=["menu"], entryPoints={"menu": "M.qml"}), "M.qml": OK.replace("function close() { opened = false }", "")}
    r = L.check(f, ALL); assert [x["rule"] for x in r] == ["USB-L01"] and "close()" in r[0]["reason"]
def test_ui_panel_base_is_fine():
    assert rules({"manifest.json": man(kinds=["panel"], entryPoints={"panel": "P.qml"}), "P.qml": "import qs.Ui\nPanel {\n}\n"}) == []
def test_local_component_root_resolved():
    f = {"manifest.json": man(kinds=["panel"], entryPoints={"panel": "P.qml"}), "P.qml": "import QtQuick\nBase {\n}\n", "Base.qml": OK}
    assert rules(f) == []
def test_service_driven_hud_skipped():
    assert rules({"manifest.json": man(kinds=["overlay", "service"], entryPoints={"overlay": "O.qml", "service": "S.qml"}), "O.qml": "import QtQuick\nItem {\n}\n", "S.qml": "import QtQuick\nItem {}\n"}) == []
def test_function_in_comment_or_string_does_not_count():
    f = {"manifest.json": man(kinds=["overlay"], entryPoints={"overlay": "O.qml"}), "O.qml": "import QtQuick\nItem {\n  // function open(p) {}\n  property string s: \"function close() {}\"\n}\n"}
    assert rules(f) == ["USB-L01"]
def test_nested_function_does_not_count():
    f = {"manifest.json": man(kinds=["overlay"], entryPoints={"overlay": "O.qml"}), "O.qml": "import QtQuick\nItem {\n  Rectangle {\n    function open(p) {}\n    function close() {}\n  }\n}\n"}
    assert rules(f) == ["USB-L01"]
def test_n01_kind_without_key():
    f = {"manifest.json": man(kinds=["bar-widget"], entryPoints={"panel": "P.qml"}), "P.qml": OK}
    assert rules(f) == ["USB-N01"]
def test_n01_kind_used_as_key():
    f = {"manifest.json": man(kinds=["bar-widget"], entryPoints={"bar-widget": "B.qml"}), "B.qml": "import QtQuick\nItem {}\n"}
    assert rules(f) == ["USB-N01"]
def test_n02_schema_version():
    f = {"manifest.json": json.dumps({"id": "a.b", "name": "x", "version": "1", "kinds": ["bar-widget"], "entryPoints": {"barWidget": "B.qml"}}), "B.qml": "Item {}\n"}
    assert rules(f) == ["USB-N02"]
    f["manifest.json"] = man(schemaVersion="1", kinds=["bar-widget"], entryPoints={"barWidget": "B.qml"}); assert rules(f) == ["USB-N02"]
def test_good_manifest_clean():
    assert rules({"manifest.json": man(kinds=["bar-widget"], entryPoints={"barWidget": "B.qml"}), "B.qml": "import QtQuick\nItem {}\n"}) == []
def test_shellroot_and_quickshell_process():
    f = {"manifest.json": man(kinds=["bar-widget"], entryPoints={"barWidget": "B.qml"}), "B.qml": "import Quickshell\nShellRoot {\n}\n"}
    assert rules(f) == ["USB-L02"]
    f["B.qml"] = "import QtQuick\nimport Quickshell.Io\nItem { Process { command: [\"quickshell\", \"-p\", \"x\"] } }\n"; assert rules(f) == ["USB-L02"]
def test_required_injected_property():
    f = {"manifest.json": man(kinds=["bar-widget"], entryPoints={"barWidget": "B.qml"}), "B.qml": "import QtQuick\nItem {\n  required property var shell\n  required property int index\n}\n"}
    r = L.check(f, ALL); assert [(x["rule"], x["line"]) for x in r] == [("USB-L03", 3)]
def test_supply_chain():
    sh = "cargo install --git https://x/y\ncargo install --git https://x/y --rev " + "a" * 40 + "\n# cargo install --git https://x/y\n"
    f = {"install.sh": sh, ".github/workflows/ci.yml": "steps:\n  - uses: actions/checkout@v4\n  - uses: actions/checkout@" + "b" * 40 + "\n  - uses: ./local\n",
         "setup.sh": "echo 'u ALL=(ALL) NOPASSWD: ALL' | sudo tee /etc/sudoers.d/u\necho 'u ALL=(root) NOPASSWD: /usr/bin/fixedhelper' > x\n"}
    r = L.check(f, ALL); assert sorted((x["rule"], x["file"], x["line"]) for x in r) == [("USB-W11", "install.sh", 1), ("USB-W12", ".github/workflows/ci.yml", 2), ("USB-W13", "setup.sh", 1)]
def test_prompt_shots_agree_with_rules():
    sys.path[:0] = [os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../train")]
    import pytest
    P = pytest.importorskip("prompt_v3", reason="prompt_v3 lives in the usuba-checker-models repo")
    for i, (inp, out) in enumerate(P.SHOTS, 1):
        hit = [x["rule"] for x in L.check(inp["files"], ALL)]
        assert (hit == ["USB-L01"]) == (i == 7), (i, hit)   # only the broken lifecycle shot fires; shot 6 (clean overlay with open/close) must not
        if i == 6: assert out["verdict"] == "approve" and "function open(" in inp["files"]["Overlay.qml"] and "function close(" in inp["files"]["Overlay.qml"]
if __name__ == "__main__":
    n = 0
    for k, v in list(globals().items()):
        if k.startswith("test_"): v(); n += 1
    print("ok", n)
