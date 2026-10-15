"""Installable entry point for the Usuba Checker (audit G).

    pip install -e ../usuba-checker-scripts                                  # local, uses the in-repo reference tree
    pip install "usuba-checker @ git+https://github.com/outboundsync/usuba-checker-scripts@<SHA>"   # pinned; set FT_OMARCHY

    import usuba_checker as uc
    rep = uc.check_files({"manifest.json": "...", "Widget.qml": "..."})      # static Checker; rep["meta"] = schema/sha/rules_hash/reference tree
    uc.holdout_ids()                                                         # public sealed-holdout repo urls
    uc.scoring                                                               # the pure eval scorer (eval/hancore_holdout/scoring.py)

Only the stable surface above is public. The Checker modules keep their bare-name imports (``import static_checks``) because
``functest/`` is put on ``sys.path`` here, exactly as the in-repo scripts do.
"""
import importlib
import importlib.util
import os
import sys

__version__ = "0.1.0"


_REPO_LAYOUT = {"usuba_checker.functest": "functest", "usuba_checker.holdout": os.path.join("eval", "hancore_holdout")}


def _pkg_dir(name):
    """Installed wheel / editable install: the mapped sub-package. Plain checkout on sys.path (no install): the repo's own directory."""
    try:
        spec = importlib.util.find_spec(name)
    except ModuleNotFoundError:
        spec = None
    if spec is not None and spec.submodule_search_locations:
        return list(spec.submodule_search_locations)[0]
    here = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), _REPO_LAYOUT[name])
    if os.path.isdir(here):
        return here
    raise ImportError(f"{name} is not installed (install usuba-checker from the repo's pyproject.toml)")


def functest_dir():
    return _pkg_dir("usuba_checker.functest")


def _activate():
    d = functest_dir()
    if d not in sys.path:
        sys.path.insert(0, d)
    return d


def check_files(files, run_runtime=False):
    """Run the Checker on ``{path: text}``. Static by default: the runtime check needs bwrap + Quickshell and is opt-in."""
    _activate()
    import functest
    from usuba import provenance
    rep = functest.test(files=files, run_runtime=run_runtime)
    rep["meta"] = dict(provenance.report_meta(), package="usuba-checker", package_version=__version__)
    return rep


def report_meta():
    _activate()
    from usuba import provenance
    return dict(provenance.report_meta(), package="usuba-checker", package_version=__version__)


def holdout_ids():
    with open(os.path.join(_pkg_dir("usuba_checker.holdout"), "plugin_ids.txt")) as f:
        return [ln.strip() for ln in f if ln.strip()]


def __getattr__(name):
    if name == "scoring":
        spec = importlib.util.spec_from_file_location("usuba_checker_scoring", os.path.join(_pkg_dir("usuba_checker.holdout"), "scoring.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    raise AttributeError(name)
