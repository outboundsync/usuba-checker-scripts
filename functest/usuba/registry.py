"""One registry of every rule id the Checker can emit (audit D4).

``rules.RULES`` is the Usuba Standard (STANDARD.md is generated from it). The HC rules (``hancore_rules_v2``), the lifecycle rules
(``lifecycle_rules``) and the Dell-learned D rules emit ids that the Standard table does not describe; they are registered here so a
test can assert that nothing is emitted without being registered (``tests/test_rule_registry.py``).

ENFORCEMENT says where a rule can change a *verdict*:
  functest   : functest.test() pass/fail (static_fails) or an advisory flag
  report     : appears in the Checker report that goes into training rows and eval prompts (models repo ``train/checker_report.py``)
Lifecycle rules (N01, N02, L01-L03) are in ``report`` only. functest.test() does NOT run ``lifecycle_rules`` (documented, deliberate:
wiring them in would change the pass/fail of every published functest result; do that as its own, versioned change).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from usuba import hancore_rules_v2, lifecycle_rules, rules  # noqa: E402

# Dell-learned rules (dell_learned.py) and the Dell severity policy.
DELL_RULES = {
    "USB-D00": "Dell severity policy: a QML message is a blocker only if it stops a component from being created (runtime.py)",
    "USB-D01": "system-audio-graph-mutation: rewires the user's global audio graph",
    "USB-D02": "toggle-entry-without-handler: panel/overlay entry point exposes no toggle()/open()/show()",
    "USB-D04": "shell died during the close/reopen usage cycle (runtime.py)",
    "USB-D05": "runaway memory: shell RSS growth after the plugin loaded (runtime.py)",
    "USB-D06": "read-only-close-path: assigns the shell's read-only centerHoverRevealSuppressed",
}


def registered():
    """{rule id: dict(source, level, title)}"""
    reg = {k: dict(source="rules.RULES", level=v[1], title=v[0]) for k, v in rules.RULES.items()}
    for k, v in hancore_rules_v2.RULES.items():
        reg.setdefault(k, dict(source="hancore_rules_v2", level="warn", title=v[1]))
    for k, v in lifecycle_rules.RULES.items():
        reg.setdefault(k, dict(source="lifecycle_rules", level="see rules.RULES", title=v[1]))
    for k, v in DELL_RULES.items():
        reg.setdefault(k, dict(source="dell_learned/runtime", level="warn", title=v))
    return reg


ENFORCEMENT = {k: ("report",) for k in lifecycle_rules.RULES}
