"""Skip conditions from the winners follow-up (docs/V3_FIXES.md) + static_checks scoping. Run: cd functest && python3 -m pytest tests/test_hc_skips.py -q"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from usuba import hancore_rules_v2 as V
import static_checks as S
ALL = set(V.RULES)
def hits(files): return sorted({f["rule"] for f in V.check(files, enabled=ALL)})
def test_curl_to_dev_null_not_hc01():
    assert "USB-HC01" not in hits({"x.sh": "#!/bin/bash\ncurl --fail --silent --max-time 4 https://a.io/ping \\\n  --user-agent x >/dev/null 2>&1 &\n"})
    assert "USB-HC01" in hits({"x.sh": "#!/bin/bash\ncurl --fail --silent --max-time 4 https://a.io/data -o out.json\n"})
def test_rm_rf_mktemp_var_not_hc06():
    assert "USB-HC06" not in hits({"x.sh": "#!/bin/bash\nd=$(mktemp -d)\nrm -rf \"$d\"\n"})
    assert "USB-HC06" in hits({"x.sh": "#!/bin/bash\nd=$1\nrm -rf \"$d\"\n"})
def test_rm_rf_regex_guarded_var_not_hc06():
    assert "USB-HC06" not in hits({"x.sh": "#!/bin/bash\n[[ $d =~ ^[a-z0-9]+$ ]] || exit 2\nrm -rf \"$d\"\n"})
def test_hyprctl_eval_not_hc24():
    f = {"x.sh": "#!/bin/bash\nsetup=$(cat <<'L'\nx=1\nL\n)\nresponse=$(hyprctl eval \"$setup\")\n"}
    assert "USB-HC24" not in hits(f)
    assert "USB-HC24" in hits({"x.sh": "#!/bin/bash\neval \"$cmd\"\n"})
def test_regex_guarded_eval_not_hc24():
    assert "USB-HC24" not in hits({"x.sh": "#!/bin/bash\n[[ $w =~ ^[0-9]+$ ]] || exit 2\neval \"resize $w\"\n"})
def test_helper_wrapped_curl_not_hc18():
    py = "import subprocess\ndef run_curl(u):\n    return subprocess.run(['curl', '--max-time', '5', '--max-filesize', '9', u])\ndef fetch(u, curl=run_curl):\n    return curl(u)\n"
    assert "USB-HC18" not in hits({"f.py": py})
def test_readline_on_regular_file_not_hc02():
    py = "import socket\ns = socket.socket()\ndef cancel(p):\n    with p.open() as stream:\n        v = stream.readline().strip()\n    return v\n"
    assert "USB-HC02" not in hits({"m.py": py})
def test_vendored_paths_skipped():
    bad = "#!/bin/bash\ncurl https://a.io/x -o /tmp/y\n"
    assert hits({"vendor/x.sh": bad}) == [] and hits({"daemon/LICENSE": "GPL", "daemon/x.sh": bad}) == []
    assert hits({"UPSTREAM.md": "Vendored from upstream in `tools/up/`.\n", "tools/up/x.sh": bad}) == []
    assert hits({"bin/x.sh": bad}) != []
def test_import_check_scoped_to_reachable_qml():
    man = '{"id":"a.b","entryPoints":{"barWidget":"B.qml"}}'
    f = {"manifest.json": man, "B.qml": "import QtQuick\nItem { Helper {} }\n", "Helper.qml": "import QtQuick\nItem {}\n", "daemon/Main.qml": "import linux 1.0\nItem {}\n"}
    assert not [x for x in S.check(f)[0] if x[0] == "bad-import"]
    f["Helper.qml"] = "import linux 1.0\nItem {}\n"
    assert [x for x in S.check(f)[0] if x[0] == "bad-import"]
def test_style_font_footgun_retired():
    f = {"manifest.json": '{"id":"a.b","entryPoints":{"barWidget":"B.qml"}}', "B.qml": "import QtQuick\nimport qs.Commons\nItem { Text { font.pixelSize: Style.font.heading } }\n"}
    assert not [x for x in S.check(f)[1] if "VPS" in x[1]]
