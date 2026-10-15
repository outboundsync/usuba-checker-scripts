"""A7/A1: the eval renders v4 prompts with the same code_blob as the r5 builders (needs a models checkout: USUBA_MODELS_DIR or a sibling dir)."""
import importlib.util
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANDS = [os.environ.get("USUBA_MODELS_DIR"), os.path.join(os.path.dirname(ROOT), "usuba-checker-models")]
TRAIN = next((os.path.join(c, "train") for c in CANDS if c and os.path.isfile(os.path.join(c, "train", "code_blob.py"))), None)
pytestmark = pytest.mark.skipif(TRAIN is None, reason="models repo checkout not found")


def test_run_eval_v4_uses_shared_renderer_and_choice_exists():
    src = open(os.path.join(ROOT, "eval", "hancore_holdout", "run_eval.py")).read()
    assert '"v4"' in src and "_cb.code_blob" in src and "required=True" in src.split('"--prompt"')[1].split("\n")[0]
    sys.path.insert(0, TRAIN)
    try:
        spec = importlib.util.spec_from_file_location("cb_parity", os.path.join(TRAIN, "code_blob.py")); cb = importlib.util.module_from_spec(spec); spec.loader.exec_module(cb)
    finally:
        sys.path.remove(TRAIN)
    files = {"manifest.json": "{}", "A.qml": "\n".join(f"line {i}" for i in range(3000)), "R.md": "x"}
    blob = cb.code_blob(files)
    assert "(truncated: showing lines 1-" in blob and blob.startswith("### manifest.json") and "   1| {}" in blob
    # label independence: the blob is a pure function of the files
    assert blob == cb.code_blob(dict(reversed(list(files.items()))))
