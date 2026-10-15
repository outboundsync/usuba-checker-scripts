"""Checker tests: plain unittest, no network, no model. Run: python3 -m unittest discover -s tests"""
import os, subprocess, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FT = os.path.join(ROOT, "functest")
sys.path.insert(0, FT)


class StandardInSync(unittest.TestCase):
    def test_standard_md_matches_rules_table(self):
        out = subprocess.run([sys.executable, "-m", "usuba.rules"], cwd=FT, capture_output=True, text=True, check=True).stdout
        with open(os.path.join(FT, "STANDARD.md")) as f:
            self.assertEqual(out, f.read(), "regenerate: cd functest && python3 -m usuba.rules > STANDARD.md")


class EmptyPluginFails(unittest.TestCase):
    def test_empty_dir_does_not_pass(self):
        import functest
        with tempfile.TemporaryDirectory() as d:
            r = functest.test(src_dir=d)
        self.assertFalse(r["pass"])
        self.assertTrue(r["categories"])


class TypesTable(unittest.TestCase):
    def test_types_json_loads(self):
        import json
        with open(os.path.join(FT, "usuba", "types.json")) as f:
            self.assertTrue(json.load(f))


class ReferenceBinaryLists(unittest.TestCase):
    def test_omarchy_bins_match_reference_tree(self):
        """functest/dell_env/omarchy_bins.txt is exactly the bin/ listing of the public Omarchy 4.0.4 reference tree (regenerate: ls dell-ref/omarchy-4.0.4/bin)."""
        want = sorted(os.listdir(os.path.join(ROOT, "dell-ref", "omarchy-4.0.4", "bin")))
        with open(os.path.join(FT, "dell_env", "omarchy_bins.txt")) as f:
            have = sorted(l.strip() for l in f if l.strip())
        self.assertEqual(have, want)

    def test_system_bins_are_generic(self):
        with open(os.path.join(FT, "dell_env", "system_bins.txt")) as f:
            words = {w for l in f if not l.startswith("#") for w in l.split()}
        self.assertIn("bash", words)
        self.assertNotIn("kenhara", " ".join(words))


if __name__ == "__main__":
    unittest.main()
