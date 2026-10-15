import functest
from usuba import policy, provenance

COND = "Item {\n  visible: root.show && x > 0\n}\n"


def test_default_keeps_pardon(monkeypatch):
    monkeypatch.delenv("FT_STRICT_D9", raising=False)
    rt = {"errors": ["bar-widget has zero size [0, 0]"]}
    functest.apply_zero_size_pardon(rt, COND)
    assert rt["errors"] == [] and "conditionally hidden" in rt["soft"][0]


def test_strict_keeps_error(monkeypatch):
    monkeypatch.setenv("FT_STRICT_D9", "1")
    rt = {"errors": ["bar-widget has zero size [0, 0]"]}
    functest.apply_zero_size_pardon(rt, COND)
    assert rt["errors"] == ["bar-widget has zero size [0, 0]"] and not rt.get("soft")


def test_policy_stamped_in_meta(monkeypatch):
    monkeypatch.setenv("FT_STRICT_D9", "yes")
    assert policy.active() == {"strict_d9": True}
    assert provenance._policy_active()["strict_d9"] is True
    monkeypatch.setenv("FT_STRICT_D9", "0")
    assert policy.active() == {"strict_d9": False}
