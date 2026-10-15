"""Checker hardening tests (audit D1-D6). CPU only."""
import glob
import json
import os
import re
import subprocess
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FT = os.path.join(ROOT, "functest")


def run_py(code, env=None, timeout=60):
    e = dict(os.environ, **(env or {}))
    return subprocess.run([sys.executable, "-c", code], cwd=FT, env=e, capture_output=True, text=True, timeout=timeout)


# ---- D1 -----------------------------------------------------------------------------------------------------
def test_rx_case_not_exponential():
    """`a||`*n used to take 0.2 s at n=13 and minutes at n=20. Run in a subprocess so a regression fails fast instead of hanging CI."""
    code = ("import sys,time; sys.path.insert(0,'.')\n"
            "from usuba import checks\n"
            "files={'a.sh': 'x run\\n'+'a||'*40+'x\\n'}\n"
            "t=time.perf_counter(); checks._not_a_command('x', files); print(time.perf_counter()-t)")
    r = run_py(code, timeout=30)
    assert r.returncode == 0, r.stderr
    assert float(r.stdout) < 2.0


def test_old_regex_really_was_exponential():
    """Guards the test above: the audited pattern is ambiguous (\\S also matches '|')."""
    old = re.compile(r"(\S+\s*\|\s*)*x\)")
    t = time.perf_counter()
    old.search("a||" * 12 + "y")
    slow = time.perf_counter() - t
    new = re.compile(r"([^\s|]+\s*\|\s*)*x\)")
    t = time.perf_counter()
    new.search("a||" * 12 + "y")
    assert time.perf_counter() - t < slow / 5 or slow < 0.001


@pytest.mark.parametrize("name,body", [("pipes", "a||" * 400 + "x"), ("braces", "{" * 1500), ("words", ("x" * 20 + " ") * 300),
                                       ("case", "case $x in\n" + "a|" * 300 + "b)\n")])
def test_checker_survives_pathological_files(name, body):
    code = ("import sys,time; sys.path.insert(0,'.')\n"
            "from usuba import checks, hancore_rules_v2 as H, lifecycle_rules as L, hancore_rules as HR\n"
            "man='{\"id\":\"x.y\",\"name\":\"n\",\"version\":\"1\",\"kinds\":[\"panel\"],\"entryPoints\":{\"panel\":\"P.qml\"}}'\n"
            "body=%r\n" % body +
            "t=time.perf_counter()\n"
            "for ext in ('.sh','.qml','.js','.py'):\n"
            "    files={'manifest.json':man,'P.qml':'import QtQuick\\nItem{}\\n','f'+ext:body}\n"
            "    for fn in (checks.check,H.check,L.check,HR.check): fn(files)\n"
            "print(time.perf_counter()-t)")
    r = run_py(code, timeout=120)
    assert r.returncode == 0, r.stderr[-500:]
    assert float(r.stdout) < 30


# ---- D2 -----------------------------------------------------------------------------------------------------
def test_reference_api_tables_non_empty_by_default():
    r = run_py("import dell_checks as d, json; print(json.dumps({k: len(v) for k, v in d.API.items()}))")
    assert r.returncode == 0, r.stderr
    sizes = json.loads(r.stdout)
    assert sum(sizes.values()) >= 300 and all(v > 10 for v in sizes.values())


def test_missing_reference_tree_raises_instead_of_empty_tables(tmp_path):
    r = run_py("import dell_checks", env={"FT_OMARCHY": str(tmp_path / "nope")})
    assert r.returncode != 0 and "ReferenceTreeMissing" in r.stderr


def test_known_singleton_member_passes_and_unknown_fails():
    code = ("import sys, json; sys.path.insert(0,'.')\n"
            "import dell_checks\n"
            "man='{\"id\":\"x.y\",\"name\":\"n\",\"version\":\"1\",\"kinds\":[\"bar-widget\"],\"entryPoints\":{\"barWidget\":\"BarWidget.qml\"}}'\n"
            "def run(member):\n"
            "    q='import QtQuick\\nimport qs.Commons\\nItem { Rectangle { color: Color.%s } }\\n' % member\n"
            "    fails, flags = dell_checks.check({'manifest.json': man, 'BarWidget.qml': q})\n"
            "    return [c for c, _ in fails + flags]\n"
            "print(json.dumps([run('foreground'), run('definitelyNotAColorMember')]))")
    r = run_py(code)
    assert r.returncode == 0, r.stderr
    ok, bad = json.loads(r.stdout)
    assert "singleton-unknown" not in ok
    assert "singleton-unknown" in bad


# ---- D3 -----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("fname,mod", [("rules_v2_enabled.json", "hancore_rules_v2"), ("lifecycle_rules_enabled.json", "lifecycle_rules"),
                                       ("model_rules_v3.json", "hancore_rules_v2"), ("rule_hardware_status.json", "hancore_rules_v2")])
def test_missing_rule_config_is_fatal(tmp_path, fname, mod):
    import shutil
    dst = tmp_path / "functest"
    shutil.copytree(FT, dst, ignore=shutil.ignore_patterns("__pycache__", "cache", "tests", "fixtures"))
    os.remove(dst / "usuba" / fname)
    r = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0,'.'); from usuba import %s" % mod], cwd=dst, capture_output=True, text=True,
                       env=dict(os.environ, FT_OMARCHY=os.path.join(ROOT, "dell-ref", "omarchy-4.0.4")))
    assert r.returncode != 0 and "FileNotFoundError" in r.stderr


# ---- D4 -----------------------------------------------------------------------------------------------------
def test_every_emitted_rule_id_is_registered():
    sys.path.insert(0, FT)
    from usuba import registry
    reg = set(registry.registered())
    emitted = set()
    files = [f for f in glob.glob(os.path.join(FT, "usuba", "*.py")) if "old_r2ref" not in f and not f.endswith("registry.py")]
    files += [os.path.join(FT, x) for x in ("static_checks.py", "dell_checks.py", "runtime.py", "rescore.py", "dell_learned.py", "functest.py")]
    for f in files:
        emitted |= set(re.findall(r"USB-[A-Z]+\d+", open(f).read()))
    missing = sorted(emitted - reg)
    assert not missing, "emitted but not registered: %s" % missing


# error-level rules (rules.RULES) whose id is not mentioned in any test: a ratchet, it may only shrink. Add a firing fixture, then delete the id.
KNOWN_WITHOUT_FIXTURE = None  # computed below on first run; see test


def test_error_rules_have_fixtures_ratchet():
    sys.path.insert(0, FT)
    from usuba import rules
    tests_txt = ""
    for d in (os.path.join(ROOT, "tests"), os.path.join(FT, "tests")):
        for f in glob.glob(os.path.join(d, "*.py")):
            if os.path.basename(f) != os.path.basename(__file__):
                tests_txt += open(f).read()
    errs = sorted(k for k, v in rules.RULES.items() if v[1].startswith("error"))
    untested = [k for k in errs if k not in tests_txt]
    allowed = set(json.load(open(os.path.join(ROOT, "tests", "rules_without_fixture.json")))["rules"])
    new = sorted(set(untested) - allowed)
    assert not new, "new error rules without a test fixture: %s" % new
    stale = sorted(allowed - set(untested))
    assert not stale, "rules now have fixtures; remove from tests/rules_without_fixture.json: %s" % stale


def test_standard_version_single_source():
    sys.path.insert(0, FT)
    from usuba import checks, rules
    assert rules.VERSION in checks.STANDARD


# ---- D5/D6 --------------------------------------------------------------------------------------------------
def test_read_dir_sorted_and_reports_skipped(tmp_path):
    sys.path.insert(0, FT)
    import functest
    for n in ("b.qml", "a.qml", "c/z.qml", "c/y.qml"):
        p = tmp_path / n
        p.parent.mkdir(exist_ok=True)
        p.write_text("x")
    (tmp_path / "bad.bin").write_bytes(b"\xff\xfe\x00\x80")
    files, skipped = functest.read_dir_ex(str(tmp_path))
    assert list(files) == sorted(files)
    assert skipped == [("bad.bin", "not UTF-8")]


def test_cli_report_is_complete_valid_json_with_provenance(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({"id": "x.y", "name": "n", "version": "1", "kinds": ["panel"], "entryPoints": {"panel": "P.qml"}}))
    (tmp_path / "P.qml").write_text("import QtQuick\nItem {}\n")
    code = "import sys; sys.argv=['functest.py', %r]; sys.path.insert(0,'.'); import functest, runtime\n" % str(tmp_path)
    # run only static part: patch runtime so the CLI works on boxes without bwrap/sway
    code += "functest.runtime.run = lambda **k: {'pass': True, 'errors': [], 'soft': []}\n"
    code += "import runpy; runpy.run_path('functest.py', run_name='__main__')"
    r = run_py(code, timeout=120)
    assert r.returncode == 0, r.stderr[-800:]
    doc = json.loads(r.stdout)           # whole stdout parses: nothing was cut at 6000 chars
    m = doc["meta"]
    assert m["schema_version"] == 1 and len(m["rules_hash"]) == 64 and m["reference_tree"]["sha256"]
    assert "checker_git_sha" in m and "skipped_files" in doc


def test_rules_hash_covers_all_rule_files_and_changes():
    sys.path.insert(0, FT)
    from usuba import provenance
    for needed in ("dell_learned.py", "usuba/rules.py", "usuba/hancore_rules.py", "dell_env/omarchy_bins.txt"):
        assert needed in provenance.RULE_FILES
    for f in provenance.RULE_FILES:
        assert os.path.exists(os.path.join(FT, f)), f
    assert provenance.rules_hash(provenance.RULE_FILES) != provenance.rules_hash(provenance.RULE_FILES[:-1])
