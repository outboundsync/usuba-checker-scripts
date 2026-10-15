"""Provenance for Checker reports and eval results (audit D6, F5): which code and which rules produced a number.

``report_meta()`` returns schema_version, checker_git_sha (+dirty flag), rules_hash and the reference-tree path/hash. Every JSON the
Checker CLI prints, and every eval result file, carries it. ``rules_hash`` covers every file that can change a verdict, including the
ones the old cache key (``FT_VERSION``) forgot: rules.py, hancore_rules*.py, dell_learned.py, omarchy_bins.txt, the enabled-lists.
"""
import hashlib
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
FUNCTEST = os.path.dirname(HERE)
REPO = os.path.dirname(FUNCTEST)
SCHEMA_VERSION = 1

# relative to functest/. A file listed here that is missing is an error (never silently skipped).
RULE_FILES = (
    "functest.py", "runtime.py", "static_checks.py", "dell_checks.py", "dell_learned.py", "refpaths.py",
    "dell_env/setup.py", "dell_env/hyprctl.py", "dell_env/binaries.py", "dell_env/system_bins.txt", "dell_env/omarchy_bins.txt",
    "dell_env/ftprobe.qml.part",
    "usuba/checks.py", "usuba/rules.py", "usuba/hancore_rules.py", "usuba/hancore_rules_v2.py", "usuba/hancore_rules_model.py",
    "usuba/lifecycle_rules.py", "usuba/types.json", "usuba/rules_v2_enabled.json", "usuba/lifecycle_rules_enabled.json",
    "usuba/model_rules_v3.json", "usuba/policy.py", "usuba/rule_hardware_status.json",
)


def rules_hash(files=RULE_FILES):
    h = hashlib.sha256()
    for rel in sorted(files):
        with open(os.path.join(FUNCTEST, rel), "rb") as f:   # FileNotFoundError on purpose
            h.update(rel.encode() + b"\0" + hashlib.sha256(f.read()).digest())
    return h.hexdigest()


def git_state(repo=REPO):
    """(sha, dirty) of the checkout, or (None, None) outside a git work tree (e.g. an exported tarball)."""
    try:
        sha = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=20).stdout.strip()
        dirty = bool(subprocess.run(["git", "-C", repo, "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True,
                                    check=True, timeout=20).stdout.strip())
        return sha, dirty
    except (OSError, subprocess.SubprocessError):
        return None, None


def _policy_active():
    from usuba import policy
    return policy.active()


def report_meta():
    import refpaths
    sha, dirty = git_state()
    root = refpaths.omarchy_root()
    return {
        "schema_version": SCHEMA_VERSION,
        "checker_git_sha": sha,
        "checker_git_dirty": dirty,
        "rules_hash": rules_hash(),
        "policies": _policy_active(),
        "reference_tree": {"path": os.path.relpath(root, REPO) if root.startswith(REPO) else root,
                           "sha256": refpaths.reference_tree_hash(root)},
    }
