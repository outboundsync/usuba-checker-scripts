#!/usr/bin/env python3
"""Re-score saved <name>.raw.jsonl files with the CURRENT shared scorer (scoring.py): no API calls, never overwrites an existing result.

  python3 rescore.py NAME [NAME ...]            writes results/NAME.rescored.json (+ prints a summary)

Rows written by the new run_eval.py hold the full model text and finish_reason and are re-classified exactly as run_eval did.
Legacy rows (before 2026-10-15) were stored cut to 20,000 characters without finish_reason: when the stored text may have been cut,
the ORIGINAL stored verdict/validity is kept (re-parsing a cut answer would turn long valid answers invalid); the row is flagged
``legacy_text_cut`` in the output so you can see how many are affected.
"""
import json
import os
import sys

H = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, H)
import scoring  # noqa: E402

LEGACY_CUT = 20000


def rescore_row(r):
    """-> scored row dict (label, gt, verdict, pred, invalid_reason, finish_reason, flags)"""
    base = dict(plugin=r.get("plugin"), label=r["label"], gt=list(r["gt"]), finish_reason=r.get("finish_reason"), usage=r.get("usage") or {})
    raw = r.get("raw")
    if "finish_reason" in r or (raw is not None and len(raw) < LEGACY_CUT):
        cl = scoring.classify_row(raw, r.get("finish_reason"))
        return dict(base, verdict=cl["verdict"], pred=cl["pred"], invalid_reason=cl["invalid_reason"], legacy_text_cut=False)
    # legacy row whose text may have been cut (or has no text, e.g. checker/dry backends): trust the stored outcome
    ok = bool(r.get("valid")) and r.get("verdict") in scoring.VERDICTS
    pred = sorted({scoring.norm_cat(c) for c in r.get("pred", [])} & scoring.SCORED_SET)
    return dict(base, verdict=r["verdict"] if ok else "invalid", pred=pred, invalid_reason=None if ok else "legacy-invalid", legacy_text_cut=raw is not None)


def rescore(name, results_dir=None, n_boot=1000):
    d = results_dir or os.path.join(H, "results")
    with open(os.path.join(d, name + ".raw.jsonl")) as f:
        rows = [rescore_row(json.loads(line)) for line in f if line.strip()]
    meta_path = os.path.join(d, name + ".json")
    meta = json.load(open(meta_path)) if os.path.exists(meta_path) else {}
    res = {k: meta[k] for k in ("name", "backend", "model", "set", "tokens_in", "tokens_out", "cost_usd", "secs_median", "secs_total", "provenance") if k in meta}
    res.update(scoring.score_rows(rows, n_boot=n_boot))
    res["rescored"] = True
    res["n_legacy_text_cut"] = sum(r["legacy_text_cut"] for r in rows)
    if "n" in meta and meta["n"] != res["n"]:
        raise ValueError("%s: raw file has %d rows but the original result says n=%d" % (name, res["n"], meta["n"]))
    out = os.path.join(d, name + ".rescored.json")
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    return res, out


def main(argv):
    if not argv:
        sys.exit(__doc__)
    for name in argv:
        res, out = rescore(name)
        print(name, "acc", res["verdict_accuracy"], "n_invalid", res["n_invalid"], "false_alarm", res["negative_false_alarm"],
              "cat_recall", res["category_recall_micro"], "->", out)


if __name__ == "__main__":
    main(sys.argv[1:])
