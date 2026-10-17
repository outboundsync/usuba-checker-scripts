"""tools/hitcheck/build_package.py: the run-artifacts root is configurable (no hardcoded /workspace/usuba-runs)."""
import importlib.util
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BP = os.path.join(ROOT, "tools", "hitcheck", "build_package.py")


def _load(env_value=None):
    old = os.environ.pop("USUBA_RUNS_DIR", None)
    if env_value is not None:
        os.environ["USUBA_RUNS_DIR"] = env_value
    try:
        spec = importlib.util.spec_from_file_location("bp_runs_dir_under_test", BP)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        os.environ.pop("USUBA_RUNS_DIR", None)
        if old is not None:
            os.environ["USUBA_RUNS_DIR"] = old


def test_default_is_relative_to_repo():
    assert _load().R == os.path.join(os.path.dirname(ROOT), "usuba-runs")


def test_env_var_overrides_default(tmp_path):
    assert _load(str(tmp_path)).R == str(tmp_path)


def test_no_hardcoded_workspace_runs_root():
    assert 'R = "/work' + 'space/usuba-runs"' not in open(BP).read()


def test_cli_arg_and_missing_dir_message(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "USUBA_RUNS_DIR"}
    p = subprocess.run([sys.executable, BP, "--runs-dir", str(tmp_path / "nope")], capture_output=True, text=True, env=env)
    assert p.returncode != 0 and "runs dir not found" in (p.stderr + p.stdout) and str(tmp_path / "nope") in (p.stderr + p.stdout)
