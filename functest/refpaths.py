"""Location of the Omarchy reference tree the Checker reads its API tables from (audit D2).

Default is the in-repo capture ``dell-ref/omarchy-4.0.4``; ``FT_OMARCHY`` overrides it (the reference build box points it at
``/opt/ft/omarchy-4.0.4``). A missing or incomplete tree is an error: the previous behaviour (silently returning empty API
tables, so valid plugins fail ``singleton-unknown``) made every off-box run wrong without any message.
"""
import hashlib
import os

HERE = os.path.dirname(os.path.abspath(__file__))
IN_REPO = os.path.normpath(os.path.join(HERE, "..", "dell-ref", "omarchy-4.0.4"))
REQUIRED = ("shell/Ui/PluginBarApi.qml", "shell/Commons/Color.qml", "shell/Commons/Style.qml",
            "shell/Commons/Util.qml", "shell/Commons/Border.qml")


class ReferenceTreeMissing(RuntimeError):
    pass


def omarchy_root():
    root = os.environ.get("FT_OMARCHY") or IN_REPO
    missing = [r for r in REQUIRED if not os.path.isfile(os.path.join(root, r))]
    if missing:
        raise ReferenceTreeMissing(
            "Omarchy reference tree %r is missing %s. The Checker refuses to run with empty API tables. "
            "Use the in-repo dell-ref/omarchy-4.0.4 (default) or point FT_OMARCHY at a complete tree." % (root, missing))
    return root


def reference_tree_hash(root=None):
    """sha256 over the (relative path, content) of the files the Checker actually reads (shell/**/*.qml)."""
    root = root or omarchy_root()
    h = hashlib.sha256()
    for r, ds, fs in os.walk(os.path.join(root, "shell")):
        ds.sort()
        for f in sorted(fs):
            if f.endswith(".qml"):
                p = os.path.join(r, f)
                h.update(os.path.relpath(p, root).encode() + b"\0")
                with open(p, "rb") as fh:
                    h.update(fh.read())
    return h.hexdigest()
