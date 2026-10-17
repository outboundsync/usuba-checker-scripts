"""The CLI runs the static checks on any machine: when the runtime stage cannot start it says so instead of crashing.
The Python API stays strict by default, so scoring jobs never silently lose the runtime stage. No network, no model."""
import contextlib, io, json, os, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "functest"))
import functest, runtime  # noqa: E402

CLIPBOARD = os.path.join(ROOT, "dell-ref", "omarchy-4.0.4", "shell", "plugins", "clipboard")
NO_RUNTIME = (False, "no Quickshell build at /opt/qs611/bin/qs (see functest/dell_env/setup.py)")
BROKEN = {
    "manifest.json": json.dumps({"id": "demo.now-playing", "name": "Now playing", "kinds": ["barWidget"], "entryPoints": {"barWidget": "Widget.qml"}}),
    "Widget.qml": "import QtQuick\nimport Quickshell\nimport Quickshell.Io\n\nItem {\n  id: root\n  Process {\n    id: p\n"
                  "    command: [\"playerctl\", \"metadata\"]\n  }\n  Timer {\n    interval: 2000; running: true; repeat: true\n"
                  "    onTriggered: p.start()\n  }\n}\n",
}


def cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = functest.main(list(argv))
    return code, out.getvalue(), err.getvalue()


@mock.patch.object(runtime, "available", return_value=NO_RUNTIME)
class StaticFallback(unittest.TestCase):
    def test_reasons_says_runtime_was_skipped(self, _):
        code, out, _err = cli(CLIPBOARD, "--reasons")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("PASS (static checks only: runtime skipped, no Quickshell build"), out)

    def test_json_report_marks_scope_static(self, _):
        code, out, _err = cli(CLIPBOARD)
        r = json.loads(out)
        self.assertEqual((code, r["scope"], r["pass"]), (0, "static", True))
        self.assertTrue(r["runtime"]["skipped"])

    def test_static_flag_matches_auto_verdict(self, _):
        _c, auto, _e = cli(CLIPBOARD, "--reasons")
        _c, static, _e = cli(CLIPBOARD, "--static", "--reasons")
        self.assertEqual(auto.split(" ")[0], static.split(" ")[0])
        self.assertTrue(static.startswith("PASS (static checks only)"))

    def test_broken_plugin_lists_rule_ids(self, _):
        with tempfile.TemporaryDirectory() as d:
            for name, text in BROKEN.items():
                with open(os.path.join(d, name), "w") as f:
                    f.write(text)
            code, out, _err = cli(d, "--reasons")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("FAIL (static checks only"), out)
        self.assertIn("[USB-A04]", out)
        self.assertIn("[USB-B05]", out)

    def test_require_runtime_raises(self, _):
        with self.assertRaises(runtime.RuntimeUnavailable):
            cli(CLIPBOARD, "--require-runtime", "--reasons")

    def test_api_default_stays_strict(self, _):
        with self.assertRaises(runtime.RuntimeUnavailable):
            functest.test(src_dir=CLIPBOARD)

    def test_api_auto_skips(self, _):
        r = functest.test(src_dir=CLIPBOARD, run_runtime="auto")
        self.assertEqual((r["scope"], r["pass"]), ("static", True))


class Usage(unittest.TestCase):
    def test_missing_dir_is_usage_error(self):
        code, out, err = cli()
        self.assertEqual((code, out), (2, ""))
        self.assertIn("usage: functest.py", err)

    def test_unknown_flag_is_usage_error(self):
        self.assertEqual(cli(CLIPBOARD, "--bogus")[0], 2)

    def test_no_manifest_needs_no_runtime(self):
        with tempfile.TemporaryDirectory() as d:
            r = functest.test(src_dir=d)   # strict default, but nothing to load: must not raise
        self.assertFalse(r["pass"])


class RunCreatesRunsDirInsideTry(unittest.TestCase):
    def test_unwritable_runs_dir_is_reported_not_raised(self):
        with tempfile.TemporaryDirectory() as d:
            ro = os.path.join(d, "ro"); os.makedirs(ro); os.chmod(ro, 0o500)
            try:
                with mock.patch.object(runtime, "RUNS", os.path.join(ro, "runs")):
                    if os.access(ro, os.W_OK):
                        self.skipTest("running as a user that can write anywhere")
                    r = runtime.run(files=BROKEN)
            finally:
                os.chmod(ro, 0o700)
        self.assertTrue(r["errors"], r)


if __name__ == "__main__":
    unittest.main()
