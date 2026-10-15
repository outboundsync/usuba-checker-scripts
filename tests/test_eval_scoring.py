"""Metric unit tests with hand-made rows (audit B1-B4, J). CPU only, no network."""
import json

import pytest

import scoring as S


def row(label, verdict, gt=(), pred=(), **kw):
    return dict(label=label, verdict=verdict, gt=list(gt), pred=list(pred), **kw)


def test_invalid_on_negative_is_not_a_correct_approval():
    rows = [row("negative", "invalid", invalid_reason="unparseable"), row("negative", "approve"), row("positive", "changes_requested")]
    m = S.score_rows(rows, n_boot=50)
    assert m["n_invalid"] == 1 and m["n_invalid_negative"] == 1
    assert m["verdict_accuracy"] == round(2 / 3, 3)          # the invalid negative is wrong, not an approval
    assert m["negative_correct_approve"] == 0.5               # 1 of 2 negatives actually approved
    assert m["negative_false_alarm"] == 0.0                   # flagged / negatives


def test_invalid_on_positive_is_wrong_too():
    m = S.score_rows([row("positive", "invalid"), row("positive", "changes_requested")], n_boot=20)
    assert m["positive_recall"] == 0.5 and m["verdict_accuracy"] == 0.5


def test_old_scorer_bug_would_have_credited_invalid():
    # the old rule: accuracy counted `not flag(r)` for every negative, so 30 invalid rows looked like approvals
    rows = [row("negative", "invalid") for _ in range(29)]
    assert S.score_rows(rows, n_boot=20)["verdict_accuracy"] == 0.0


def test_undefined_metrics_are_none_not_zero():
    m = S.score_rows([row("positive", "changes_requested")], n_boot=20)
    assert m["negative_false_alarm"] is None and m["negative_correct_approve"] is None
    assert m["category_recall_micro"] is None and m["ci95"] is None
    assert all(v["recall"] is None for v in m["per_category"].values())


def test_empty_rows_do_not_raise():
    m = S.score_rows([], n_boot=10)
    assert m["n"] == 0 and m["verdict_accuracy"] is None


def test_expected_n_is_asserted():
    with pytest.raises(ValueError):
        S.score_rows([row("positive", "approve")], expected_n=2)


def test_bad_verdict_label_rejected():
    with pytest.raises(ValueError):
        S.score_rows([row("positive", "maybe")])


def test_per_category_counts_and_precision():
    rows = [row("positive", "changes_requested", gt=["secrets-credentials"], pred=["secrets-credentials", "url-scheme-network"]),
            row("positive", "changes_requested", gt=["secrets-credentials"], pred=[])]
    m = S.score_rows(rows, n_boot=20)
    c = m["per_category"]["secrets-credentials"]
    assert c == dict(gt=2, recall=0.5, precision=1.0)
    assert m["per_category"]["url-scheme-network"]["precision"] == 0.0
    assert m["per_category"]["scope-policy-duplicate"] == dict(gt=0, recall=None, precision=None)


def test_always_flag_baseline_reported():
    rows = [row("positive", "changes_requested")] * 3 + [row("negative", "changes_requested")]
    m = S.score_rows(rows, n_boot=20)
    assert m["always_flag_accuracy"] == 0.75 and m["verdict_accuracy"] == 0.75 and m["negative_false_alarm"] == 1.0


def test_length_stops_counted():
    m = S.score_rows([row("positive", "invalid", finish_reason="length", invalid_reason="truncated"),
                      row("positive", "changes_requested", finish_reason="stop")], n_boot=10)
    assert m["n_length_stop"] == 1


# ---- parsing / schema ---------------------------------------------------------------------------------------
GOOD = json.dumps({"verdict": "approve", "load": "works", "findings": []})


def test_classify_good_and_prose_wrapped():
    assert S.classify_row(GOOD)["verdict"] == "approve"
    assert S.classify_row("Here you go:\n```json\n" + GOOD + "\n```\nthanks")["verdict"] == "approve"
    assert S.classify_row("<think>{\"verdict\": 1}</think>" + GOOD)["verdict"] == "approve"


@pytest.mark.parametrize("raw,why", [
    ("ERROR HTTPError", "error"), ("SKIPPED max-cost", "skipped"), ("", "unparseable"), ("no json here", "unparseable"),
    ('{"verdict": "ok", "findings": []}', "schema"), ('{"verdict": "approve"}', "schema"),
    ('{"verdict": "approve", "findings": [{"category": 3}]}', "schema"),
    ('{"verdict": "approve", "findings": [{"category": "x", "line": "4"}]}', "schema"),
])
def test_invalid_reasons(raw, why):
    r = S.classify_row(raw)
    assert r["verdict"] == "invalid" and r["invalid_reason"].startswith(why)


def test_truncated_by_finish_reason_is_invalid_even_if_json_parses():
    assert S.classify_row(GOOD, finish_reason="length")["invalid_reason"] == "truncated"


def test_greedy_regex_bug_fixed_two_objects():
    raw = GOOD + "\nand another {not json}"
    assert S.classify_row(raw)["verdict"] == "approve"   # the old greedy \{.*\} swallowed both and failed


def test_norm_cat_exact_and_alias_no_substring():
    assert S.norm_cat("secrets-credentials") == "secrets-credentials"
    assert S.norm_cat("Secrets") == "secrets-credentials"
    assert S.norm_cat("Shell/Lua injection") == "shell-lua-injection"
    assert S.norm_cat("in-use:missing-binary") == "in-use:missing-binary"
    # the old first-substring matcher mapped all of these wrongly
    for bad in ("curl", "uninstall", "sql injection", "requires root permission", "permission", None, 5):
        assert S.norm_cat(bad) == "unknown", bad


def test_also_field_honoured():
    out = {"verdict": "changes_requested", "findings": [{"category": "secrets", "also": ["url-scheme-network"]}]}
    assert S.predicted_cats(out) == {"secrets-credentials", "url-scheme-network"}


# ---- statistics ---------------------------------------------------------------------------------------------
def _cohort(n_pos, n_neg, neg_flag):
    rows = [row("positive", "changes_requested") for _ in range(n_pos)]
    rows += [row("negative", "changes_requested" if i < neg_flag else "approve") for i in range(n_neg)]
    return rows


def test_bootstrap_ci_wide_for_29_negatives_and_deterministic():
    rows = _cohort(300, 29, 27)
    a = S.score_rows(rows, n_boot=400, seed=1)["ci95"]["negative_false_alarm"]
    b = S.score_rows(rows, n_boot=400, seed=1)["ci95"]["negative_false_alarm"]
    assert a == b                                   # seeded
    assert a[0] < 0.931 < a[1] and a[1] - a[0] > 0.10   # about +-7 points around 27/29 (audit B4: CI is wide)


def test_mcnemar_exact():
    b, c, p = S.mcnemar_exact([1, 1, 1, 0, 0, 1], [0, 0, 0, 0, 0, 1])
    assert (b, c) == (3, 0) and abs(p - 0.25) < 1e-9
    assert S.mcnemar_exact([1, 0], [1, 0])[2] == 1.0


def test_paired_bootstrap_detects_no_difference():
    rows = _cohort(50, 10, 5)
    d, lo, hi = S.paired_bootstrap_diff(rows, rows, n_boot=100)
    assert d == 0.0 and lo == 0.0 and hi == 0.0
