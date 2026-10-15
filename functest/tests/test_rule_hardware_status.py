"""Rules never observed breaking a plugin on hardware must not be labelled as such. Run: cd functest && python3 -m pytest tests/test_rule_hardware_status.py -q"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from usuba import hancore_rules_v2 as V
def test_every_hit_checked_rule_is_enabled_and_labelled_consistently():
    for r, s in V.HARDWARE_STATUS.items():
        assert r in V.RULES or r[4] in "LN", r  # lifecycle rules live in lifecycle_rules.py
        assert s["breaks_on_hardware"] == (s["direct"] > 0 and s["hardware_evidence"].startswith("observed")), r
        if s["direct"] == 0:
            assert not s["breaks_on_hardware"], r
def test_known_findings():
    st = V.HARDWARE_STATUS
    assert st["USB-HC01"]["direct"] == 20 and st["USB-HC17"]["breaks_on_hardware"] is False and st["USB-HC16"]["hardware_evidence"] == "static_only"
