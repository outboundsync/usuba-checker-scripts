"""A7/A1 + audit 8: the eval renders v4 prompts with the canonical usuba_checker.code_blob that lives in THIS repo
(usuba-checker-models imports it from the pinned package; it has no copy)."""
import hashlib
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from usuba_checker import code_blob as cb  # noqa: E402

# golden hash of the rendered blob for a fixed input: any edit to the renderer must be a deliberate, reviewed change (models repo carries the same constant)
FILES = {"manifest.json": "{}", "A.qml": "\n".join(f"line {i}" for i in range(3000)), "R.md": "x"}
GOLDEN = "550fdf939cbc2de91376956c5feed36da9c51235e70af6b0ed829f08a4f868bd"


def test_run_eval_v4_uses_package_renderer_not_a_copy():
    src = open(os.path.join(ROOT, "eval", "hancore_holdout", "run_eval.py")).read()
    assert "from usuba_checker import code_blob as _cb" in src and "import code_blob as _cb" not in src.replace("from usuba_checker import code_blob as _cb", "")
    assert "required=True" in src.split('"--prompt"')[1].split("\n")[0]


def test_blob_shape_and_label_independence():
    blob = cb.code_blob(FILES)
    assert "(truncated: showing lines 1-" in blob and blob.startswith("### manifest.json") and "   1| {}" in blob
    assert blob == cb.code_blob(dict(reversed(list(FILES.items()))))


def test_golden_hash():
    assert hashlib.sha256(cb.code_blob(FILES).encode()).hexdigest() == GOLDEN
