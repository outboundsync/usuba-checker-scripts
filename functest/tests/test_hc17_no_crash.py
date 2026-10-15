"""USB-HC17 used to raise AttributeError ('bool' has no attribute 'group') on npm/pip/npx install lines. Run: cd functest && python3 -m pytest tests/test_hc17_no_crash.py -q"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from usuba import hancore_rules_v2 as V
def hits(files): return sorted({f["rule"] for f in V.check(files, enabled=set(V.RULES))})
def test_install_lines_do_not_raise_and_still_hit():
    for ln in ("npm install -g somepkg", "pip install requests", "npx some-tool run", "pipx install foo", "uvx ruff check"):
        assert "USB-HC17" in hits({"setup.sh": "#!/bin/bash\n" + ln + "\n"}), ln
def test_pinned_install_is_quiet():
    for ln in ("npm install -g somepkg@1.2.3", "pip install requests==2.31.0", "npx some-tool@1.0.0 run"):
        assert "USB-HC17" not in hits({"setup.sh": "#!/bin/bash\n" + ln + "\n"}), ln
