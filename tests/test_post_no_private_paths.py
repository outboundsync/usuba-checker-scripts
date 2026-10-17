"""docs/post is public: it must not carry private box paths, home-directory paths or private repo/mirror names (the [TK] placeholders stay)."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POST = os.path.join(ROOT, "docs", "post")
# built from parts so this file does not match itself
PRIVATE = re.compile("|".join([
    "/work" + "space", "/home" + r"/[a-z0-9_-]+/", "/Users" + "/", "usuba-" + "runs", "usuba-" + "backups",
    "scripts-" + "private", "model-" + "private", r"\.mirror\b", "usuba-model-" + "checker",
]))
TEXT = (".md", ".csv", ".py", ".json", ".txt")


def test_no_private_paths_in_public_post_files():
    bad = []
    for r, _, fs in os.walk(POST):
        for f in fs:
            if f.endswith(TEXT):
                p = os.path.join(r, f)
                for i, line in enumerate(open(p, encoding="utf-8", errors="replace"), 1):
                    if PRIVATE.search(line):
                        bad.append(f"{os.path.relpath(p, ROOT)}:{i}")
    assert not bad, bad


def test_tk_placeholders_are_kept():
    assert "[TK" in open(os.path.join(POST, "draft.md"), encoding="utf-8").read()
