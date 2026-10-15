"""Audit G: the wheel is installable from pyproject.toml and the Checker runs from the installed copy (not from the checkout)."""
import glob
import os
import subprocess
import sys
import zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pytest.importorskip("setuptools")


@pytest.fixture(scope="module")
def installed(tmp_path_factory):
    out = tmp_path_factory.mktemp("whl")
    r = subprocess.run([sys.executable, "-m", "pip", "wheel", ROOT, "--no-deps", "--no-build-isolation", "-q", "-w", str(out)],
                       capture_output=True, text=True, check=False, cwd=str(out))
    if r.returncode != 0:
        pytest.skip("cannot build a wheel here: " + r.stderr[-300:])
    whl = glob.glob(str(out / "*.whl"))[0]
    dest = out / "site"
    with zipfile.ZipFile(whl) as z:
        z.extractall(dest)
        names = z.namelist()
    return str(dest), names


def test_wheel_contents(installed):
    _, names = installed
    assert "usuba_checker/functest/usuba/checks.py" in names
    assert "usuba_checker/holdout/plugin_ids.txt" in names
    assert not any(n.startswith("usuba_checker/functest/results") for n in names)    # the 1 MB committed result file is not shipped
    assert not any("dell-ref" in n for n in names)                                    # reference tree: FT_OMARCHY / in-repo only


def test_checker_runs_from_installed_copy(installed, tmp_path):
    site, _ = installed
    code = ("import json, usuba_checker as uc\n"
            "r = uc.check_files({'manifest.json': '{\"id\": \"a.b\"}', 'W.qml': 'import QtQuick\\nItem {}'})\n"
            "print(json.dumps({'meta': r['meta'], 'ids': len(uc.holdout_ids()), 'slugs': len(uc.scoring.SCORED)}))\n")
    env = dict(os.environ, PYTHONPATH=site, FT_OMARCHY=os.path.join(ROOT, "dell-ref", "omarchy-4.0.4"))
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd=str(tmp_path), check=False)
    assert r.returncode == 0, r.stderr[-800:]
    import json
    d = json.loads(r.stdout.strip().splitlines()[-1])
    assert d["ids"] == 329 and d["slugs"] == 13
    assert d["meta"]["package"] == "usuba-checker" and len(d["meta"]["rules_hash"]) == 64 and d["meta"]["reference_tree"]["sha256"]


def test_missing_reference_tree_is_an_error_not_empty_tables(installed, tmp_path):
    site, _ = installed
    env = dict(os.environ, PYTHONPATH=site)
    env.pop("FT_OMARCHY", None)
    # installed copy has no in-repo dell-ref next to it: it must refuse instead of silently running with empty API tables
    r = subprocess.run([sys.executable, "-c", "import usuba_checker as uc; uc.report_meta()"], capture_output=True, text=True, env=env,
                       cwd=str(tmp_path), check=False)
    assert r.returncode != 0 and "reference tree" in r.stderr.lower()
