"""code_blob/v2: anchored windows are additive (render() bytes unchanged), deterministic and bounded."""
from usuba_checker import code_blob as CB

BIG = "\n".join("line %d = %s" % (i, "x" * 40) for i in range(1, 1200))
FILES = {"manifest.json": "{}", "a.sh": BIG}


def test_render_unchanged_and_windows_additive():
    b0, i0 = CB.render(FILES)
    assert not CB.line_visible(i0, "a.sh", 1000)
    b, i = CB.render_anchored(FILES, [("a.sh", 1000)])
    assert b.startswith(b0) and CB.line_visible(i, "a.sh", 1000) and "[window lines" in b
    assert CB.render_anchored(FILES, [("a.sh", 3)])[0] == b0 and CB.render_anchored(FILES, [])[0] == b0
    assert CB.render_anchored(FILES, [("a.sh", 1000)])[0] == b


def test_window_budget():
    b, i = CB.render_anchored(FILES, [("a.sh", 300 + 60 * k) for k in range(14)])
    assert len(i["a.sh"]["windows"]) <= CB.MAX_WINDOWS and len(b) - len(CB.render(FILES)[0]) <= CB.ANCHOR_CAP + 2000
