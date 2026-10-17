"""Every rule id that the Checker code can emit is registered in functest/usuba/registry.py (audit D4).

Static check: collects every ``USB-<letters><digits>`` string literal from the Checker modules and requires it in ``registry.registered()``.
Also checks that the registry entries are well formed and that the lifecycle rules are marked report-only.
"""
import glob
import os
import re

from usuba import registry

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ID = re.compile(r"""["'](USB-[A-Z]+\d+)["']""")
SKIP = {"registry.py"}


def _emitted():
    ids = {}
    for pat in ("functest/*.py", "functest/usuba/*.py"):
        for f in glob.glob(os.path.join(ROOT, pat)):
            name = os.path.basename(f)
            if name in SKIP or name.startswith(("recal_", "calibrate", "old_scores")):
                continue
            with open(f, encoding="utf-8") as fh:
                for m in ID.finditer(fh.read()):
                    ids.setdefault(m.group(1), name)
    return ids


def test_every_emitted_rule_id_is_registered():
    reg = registry.registered()
    missing = {k: v for k, v in _emitted().items() if k not in reg}
    assert not missing, f"rule ids used in code but not in registry.py: {missing}"


def test_registry_entries_are_well_formed():
    for k, v in registry.registered().items():
        assert k.startswith("USB-") or re.match(r"^[A-Z]+\d+$", k), k
        assert v["source"] and v["title"], k


def test_lifecycle_rules_are_report_only():
    assert set(registry.ENFORCEMENT) == set(registry.lifecycle_rules.RULES)
    assert all(v == ("report",) for v in registry.ENFORCEMENT.values())
