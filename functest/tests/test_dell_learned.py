#!/usr/bin/env python3
"""Unit tests for the Dell-learned checks (USB-D01/D02), the Dell severity rule, and the USB-D05/D04 runtime parsing hooks.
run: python3 -m unittest functest/tests/test_dell_learned.py"""
import json, os, re, sys, unittest, importlib.util
HERE = os.path.dirname(os.path.abspath(__file__)); FT = os.path.dirname(HERE); sys.path.insert(0, FT)
import dell_learned
def man(**kw): return json.dumps(dict(dict(id="t.p", schemaVersion=1, kinds=["panel"], entryPoints={"panel": "Panel.qml"}), **kw))
class D01(unittest.TestCase):
    def test_fires_on_default_sink_rewire(self):
        f = {"manifest.json": man(), "Panel.qml": "Item { function toggle(){} }", "eq.sh": "pw-metadata -n default 42 target.object 7 Spa:Id\n"}
        self.assertIn("USB-D01", {x["rule"] for x in dell_learned.check(f)})
    def test_fires_on_pactl_load_module(self):
        f = {"manifest.json": man(), "Panel.qml": 'Item { function toggle(){} Process { command: ["pactl","load-module","module-null-sink"] } }'}
        self.assertIn("USB-D01", {x["rule"] for x in dell_learned.check(f)})
    def test_read_only_audio_is_fine(self):
        f = {"manifest.json": man(), "Panel.qml": 'Item { function toggle(){} Process { command: ["wpctl","get-volume","@DEFAULT_AUDIO_SINK@"] } }'}
        self.assertNotIn("USB-D01", {x["rule"] for x in dell_learned.check(f)})
    def test_comment_ignored(self):
        f = {"manifest.json": man(), "Panel.qml": "Item { function toggle(){} // pactl load-module module-loopback\n}"}
        self.assertNotIn("USB-D01", {x["rule"] for x in dell_learned.check(f)})
    def test_is_warning(self):
        f = {"manifest.json": man(), "a.sh": "wpctl set-default 51"}
        self.assertEqual([x["severity"] for x in dell_learned.check(f) if x["rule"] == "USB-D01"], ["medium"])
class Robustness(unittest.TestCase):
    def test_non_string_kinds_do_not_crash(self):
        # regression: a manifest with dict entries in "kinds" raised TypeError (unhashable dict) and aborted eval_dell.py
        f = {"manifest.json": man(kinds=[{"type": "panel"}, "panel"]), "Panel.qml": "PanelWindow { visible: false }"}
        self.assertIn("USB-D02", {x["rule"] for x in dell_learned.check(f)})
        f = {"manifest.json": man(kinds="panel"), "Panel.qml": "PanelWindow { }"}
        dell_learned.check(f)
class D06(unittest.TestCase):
    def test_assignment_fires(self):
        f = {"manifest.json": man(), "Panel.qml": "PanelWindow { function toggle(){} function close(){ bar.centerHoverRevealSuppressed = false; visible = false } }"}
        self.assertEqual([x["severity"] for x in dell_learned.check(f) if x["rule"] == "USB-D06"], ["medium"])
    def test_setter_fires(self):
        f = {"manifest.json": man(), "Panel.qml": "PanelWindow { function toggle(){ shell.setCenterHoverRevealSuppressed(true) } }"}
        self.assertIn("USB-D06", {x["rule"] for x in dell_learned.check(f)})
    def test_read_and_comparison_do_not_fire(self):
        f = {"manifest.json": man(), "Panel.qml": "PanelWindow { function toggle(){} property bool x: bar.centerHoverRevealSuppressed == true // centerHoverRevealSuppressed = 1\n}"}
        self.assertNotIn("USB-D06", {x["rule"] for x in dell_learned.check(f)})
class D02(unittest.TestCase):
    def test_panel_without_toggle(self):
        f = {"manifest.json": man(), "Panel.qml": "PanelWindow { visible: false }"}
        self.assertIn("USB-D02", {x["rule"] for x in dell_learned.check(f)})
    def test_panel_with_toggle(self):
        f = {"manifest.json": man(), "Panel.qml": "PanelWindow { function toggle() { visible = !visible } }"}
        self.assertNotIn("USB-D02", {x["rule"] for x in dell_learned.check(f)})
    def test_overlay_with_ipc_handler(self):
        f = {"manifest.json": man(kinds=["overlay"], entryPoints={"overlay": "O.qml"}), "O.qml": "Item { IpcHandler { target: 'x' } }"}
        self.assertNotIn("USB-D02", {x["rule"] for x in dell_learned.check(f)})
    def test_bar_widget_not_checked(self):
        f = {"manifest.json": man(kinds=["bar-widget", "panel"], entryPoints={"panel": "Panel.qml", "barWidget": "W.qml"}), "Panel.qml": "Item {}", "W.qml": "Item {}"}
        self.assertNotIn("USB-D02", {x["rule"] for x in dell_learned.check(f)})
@unittest.skipUnless(os.path.exists(os.path.join(os.path.dirname(FT), "dell", "sweep", "build_results.py")), "needs the private device-sweep tooling (not published)")
class SeverityRule(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        src = open(os.path.join(os.path.dirname(FT), "dell", "sweep", "build_results.py")).read()
        cls.FATAL = re.compile(re.search(r'FATAL = _re\.compile\(r"(.*?)", _re\.I\)', src).group(1).encode().decode("unicode_escape"), re.I)
    def test_cosmetic_from_answer_key(self):
        for m in ("Panel.qml[317:21]: Unable to assign [undefined] to int",
                  'Panel.qml[119:-1]: TypeError: Cannot assign to read-only property "centerHoverRevealSuppressed"',
                  "Panel.qml[40:-1]: ReferenceError: ShellColor is not defined",
                  "QML ScrollView at RamManager.qml[201:7]: Cannot anchor to an item that isn't a parent or sibling."):
            self.assertIsNone(self.FATAL.search(m), m)
    def test_fatal(self):
        for m in ("Widget.qml:3:1: module \"Quickshell.Services.Foo\" is not installed", "Panel.qml:12:5: Fancy is not a type",
                  "Bar.qml:9: SyntaxError: Expected token `}'", "Failed to load component Panel.qml"):
            self.assertIsNotNone(self.FATAL.search(m), m)
class RuntimeHooks(unittest.TestCase):
    def test_driver_has_usage_cycle_and_rss(self):
        import runtime
        self.assertIn('emit M0 ps -o rss=', runtime.DRIVER); self.assertIn('echo "U usage-begin"', runtime.DRIVER); self.assertIn("emit P3", runtime.DRIVER)
        self.assertEqual((runtime.MEM_FAIL_MB, runtime.MEM_WARN_MB), (300, 150))
if __name__ == "__main__": unittest.main()
