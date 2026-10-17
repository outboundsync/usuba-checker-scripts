"""Rule messages quote the Omarchy package version (4.0.4-1), not the tree's own version file string (4.0.0.alpha)."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = ["functest/runtime.py", "functest/dell_checks.py"]


def test_emitted_messages_use_package_version():
    for f in FILES:
        for i, line in enumerate(open(os.path.join(ROOT, f), encoding="utf-8"), 1):
            if "4.0.0." + "alpha" in line:
                assert "version file" in line, f"{f}:{i} quotes the tree version file string as the Omarchy version"
    assert "Omarchy 4.0.4-1 bin + system" in open(os.path.join(ROOT, "functest/runtime.py"), encoding="utf-8").read()
    assert "PluginBarApi member on Omarchy 4.0.4-1" in open(os.path.join(ROOT, "functest/dell_checks.py"), encoding="utf-8").read()
