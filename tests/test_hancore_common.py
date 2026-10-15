import json

from hancore import common

A = "a" * 40
B = "b" * 40
C = "c" * 40
P = "https://github.com/own/plug"


def _row(text, t, typ="finding"):
    return dict(plugin=P, thread="t", thread_title="x", thread_repo="omacom/omarchy-plugin-marketplace", thread_author="a", url="u" + str(t), kind="k",
                date=f"2026-01-0{t}", heading="", text=text, code="", fixed="fixed:x", fixed_evidence_url="", fixed_evidence="", labels=[],
                item_type=typ, categories=["secrets-credentials"])


def _load(tmp_path, monkeypatch, rows, strict):
    p = tmp_path / "r.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows))
    monkeypatch.setattr(common, "REV", str(p))
    return common.load(strict_sha=strict)[P]


def test_reviewed_shas_skips_fix_sentences_and_foreign_commit_urls():
    assert common.reviewed_shas(f"Blocked at `{A}` because x") == [A]
    assert common.reviewed_shas(f"The issue is fixed in commit {B}") == []
    assert common.reviewed_shas(f"see https://github.com/other/repo/commit/{C}", "own/plug") == []
    assert common.reviewed_shas(f"see https://github.com/own/plug/commit/{C}", "own/plug") == [C]


def test_strict_attribution_differs_only_when_asked(tmp_path, monkeypatch):
    rows = [_row(f"Blocked at `{A}`: token in file", 1), _row(f"x was fixed in commit {B}", 2), _row(f"y was fixed in commit {B}", 3)]
    assert _load(tmp_path, monkeypatch, rows, strict=False)["sha"] == B     # historical: most common 40-hex wins, so the FIXED sha is "reviewed"
    assert _load(tmp_path, monkeypatch, rows, strict=True)["sha"] == A
