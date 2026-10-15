"""Pure scoring for the Usuba holdout / Dell-key evals (audit B1-B4).

No I/O, no network, no globals that change: ``run_eval.py``, ``rescore.py`` (and the midcheck in the models repo) all call
the functions here, so a number can only differ between them if the *inputs* differ.

Row verdicts are three-way: ``approve``, ``changes_requested`` or ``invalid``. ``invalid`` (transport error, skipped row,
context overflow, truncated or unparseable output, schema violation) is wrong for both classes, so a model that fails to
answer on a clean plugin is *not* credited with a correct approval.
"""
import json
import random
import re

SCHEMA_VERSION = 1

SCORED = (
    "unbounded-input-resource", "install-deps-packaging", "file-safety-symlink-perms", "secrets-credentials",
    "privileged-system", "process-lifecycle-timeouts", "remote-code-pinning", "url-scheme-network",
    "rich-text-markup-injection", "shell-lua-injection", "user-config-modification", "scope-policy-duplicate",
    "listing-metadata-docs",
)
SCORED_SET = frozenset(SCORED)
# Slugs the prompts may emit that are valid but not scored.
OTHER_SLUGS = frozenset({"runtime-qml-api-compat", "other"})
# Namespaced families (in-use:missing-binary, load:component-not-created, ...): valid, unscored, kept verbatim.
FAMILIES = ("in-use:", "load:", "checker:", "runtime:", "qml:")
UNKNOWN = "unknown"

# Exact alias table (key = normalised label: lower case, '_' and runs of spaces -> '-'). NO substring matching:
# "curl", "uninstall" or "sql injection" are NOT aliases and map to ``unknown``.
ALIASES = {
    "unbounded-input-resources": "unbounded-input-resource", "unbounded-input": "unbounded-input-resource",
    "unbounded-resources": "unbounded-input-resource", "unbounded-input/resources": "unbounded-input-resource",
    "install/dependency/packaging": "install-deps-packaging", "install-dependency-packaging": "install-deps-packaging",
    "install/deps/packaging": "install-deps-packaging", "install-deps": "install-deps-packaging",
    "dependencies": "install-deps-packaging", "packaging": "install-deps-packaging", "install": "install-deps-packaging",
    "file-safety": "file-safety-symlink-perms", "file-safety-(symlinks,-permissions)": "file-safety-symlink-perms",
    "file-safety-symlinks-permissions": "file-safety-symlink-perms", "symlinks": "file-safety-symlink-perms",
    "file-permissions": "file-safety-symlink-perms",
    "secrets": "secrets-credentials", "credentials": "secrets-credentials", "secrets/credentials": "secrets-credentials",
    "privileged-or-system-changes": "privileged-system", "privileged/system-changes": "privileged-system",
    "system-changes": "privileged-system", "privileged": "privileged-system", "privilege-escalation": "privileged-system",
    "process-lifecycle/timeouts": "process-lifecycle-timeouts", "process-lifecycle": "process-lifecycle-timeouts",
    "timeouts": "process-lifecycle-timeouts", "lifecycle": "process-lifecycle-timeouts",
    "remote-code-and-pinning": "remote-code-pinning", "remote-code/pinning": "remote-code-pinning",
    "remote-code": "remote-code-pinning", "pinning": "remote-code-pinning",
    "url/network-handling": "url-scheme-network", "url-network-handling": "url-scheme-network",
    "url-handling": "url-scheme-network", "network-handling": "url-scheme-network", "url/network": "url-scheme-network",
    "rich-text/markup-injection": "rich-text-markup-injection", "markup-injection": "rich-text-markup-injection",
    "rich-text-injection": "rich-text-markup-injection", "rich-text": "rich-text-markup-injection",
    "shell/lua-injection": "shell-lua-injection", "shell-injection": "shell-lua-injection",
    "command-injection": "shell-lua-injection", "lua-injection": "shell-lua-injection",
    "user-config": "user-config-modification", "user-config-modifications": "user-config-modification",
    "scope/policy": "scope-policy-duplicate", "scope-policy": "scope-policy-duplicate",
    "scope-and-policy": "scope-policy-duplicate", "scope-policy/duplicate": "scope-policy-duplicate",
    "listing/metadata/docs": "listing-metadata-docs", "listing-metadata": "listing-metadata-docs",
}
VERDICTS = ("approve", "changes_requested")
SEVERITIES = ("blocker", "warning")
LOADS = ("works", "broken", "unsure")


def norm_cat(c):
    """Exact slug, family-prefixed label, or alias -> canonical label; anything else -> ``unknown``."""
    if not isinstance(c, str):
        return UNKNOWN
    k = re.sub(r"[_\s]+", "-", c.strip().lower())
    if k in SCORED_SET or k in OTHER_SLUGS:
        return k
    if k.startswith(FAMILIES):
        return k
    return ALIASES.get(k, UNKNOWN)


# ---- output schema (hand-validated: no jsonschema dependency) -------------------------------------------------
OUTPUT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["verdict", "findings"],
    "properties": {
        "verdict": {"enum": list(VERDICTS)},
        "load": {"enum": list(LOADS) + [None]},
        "findings": {"type": "array", "items": {
            "type": "object", "required": ["category"],
            "properties": {
                "category": {"type": "string"}, "severity": {"enum": list(SEVERITIES)},
                "file": {"type": ["string", "null"]}, "line": {"type": ["integer", "null"]},
                "finding": {"type": "string"}}}},
    },
}


def validate_output(out):
    """Return a list of schema violations (empty = valid) for a parsed model answer."""
    if not isinstance(out, dict):
        return ["not an object"]
    errs = []
    if out.get("verdict") not in VERDICTS:
        errs.append("verdict must be one of %s" % (VERDICTS,))
    if "load" in out and out["load"] not in LOADS + (None,):
        errs.append("bad load")
    fs = out.get("findings")
    if not isinstance(fs, list):
        errs.append("findings must be a list")
        return errs
    for i, f in enumerate(fs):
        if not isinstance(f, dict):
            errs.append("findings[%d] not an object" % i)
            continue
        if not isinstance(f.get("category"), str):
            errs.append("findings[%d].category must be a string" % i)
        if "severity" in f and f["severity"] not in SEVERITIES:
            errs.append("findings[%d].severity bad" % i)
        if f.get("file") is not None and not isinstance(f.get("file"), str):
            errs.append("findings[%d].file bad" % i)
        ln = f.get("line")
        if ln is not None and (not isinstance(ln, int) or isinstance(ln, bool)):
            errs.append("findings[%d].line bad" % i)
    return errs


def extract_json(txt):
    """First balanced JSON object in ``txt`` that parses (handles <think> blocks, ``` fences, leading prose). None if none."""
    txt = re.sub(r"<think>.*?</think>", "", txt or "", flags=re.S).strip()
    dec = json.JSONDecoder()
    for m in re.finditer(r"\{", txt):
        try:
            obj, _ = dec.raw_decode(txt[m.start():])
        except ValueError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def parse_answer(raw, finish_reason=None):
    """Classify one raw model answer. Returns ``(out, invalid_reason)``; exactly one of them is None."""
    raw = raw or ""
    if raw.startswith("ERROR "):
        return None, "error"
    if raw.startswith("SKIPPED"):
        return None, "skipped"
    if finish_reason == "length":
        return None, "truncated"
    out = extract_json(raw)
    if out is None:
        return None, "unparseable"
    errs = validate_output(out)
    if errs:
        return None, "schema: " + errs[0]
    return out, None


def predicted_cats(out):
    """Canonical categories named by a validated answer (``also`` is honoured when present)."""
    pred = set()
    for f in (out or {}).get("findings", []):
        pred.add(norm_cat(f.get("category")))
        for c in f.get("also") or []:
            if isinstance(c, str):
                pred.add(norm_cat(c))
    return pred


def classify_row(raw, finish_reason=None):
    """raw model text -> dict(verdict, invalid_reason, pred). ``verdict`` is approve | changes_requested | invalid."""
    out, why = parse_answer(raw, finish_reason)
    if out is None:
        return dict(verdict="invalid", invalid_reason=why, pred=[])
    return dict(verdict=out["verdict"], invalid_reason=None, pred=sorted(predicted_cats(out) & SCORED_SET))


def row_correct(r):
    """Verdict correctness for one scored row; ``invalid`` is wrong for both classes."""
    if r["verdict"] == "invalid":
        return False
    return (r["verdict"] == "changes_requested") == (r["label"] == "positive")


def _rate(num, den):
    return None if not den else num / den


def _r(x, nd=3):
    return None if x is None else round(x, nd)


def point_metrics(rows):
    """Metrics (unrounded, ``None`` when undefined) for rows with keys label, verdict, gt, pred."""
    pos = [r for r in rows if r["label"] == "positive"]
    neg = [r for r in rows if r["label"] == "negative"]
    flag = lambda r: r["verdict"] == "changes_requested"
    tp = gtn = prn = 0
    for r in rows:
        g, p = set(r["gt"]) & SCORED_SET, set(r["pred"]) & SCORED_SET
        tp += len(g & p)
        gtn += len(g)
        prn += len(p)
    return dict(
        verdict_accuracy=_rate(sum(row_correct(r) for r in rows), len(rows)),
        positive_recall=_rate(sum(flag(r) for r in pos), len(pos)),
        negative_false_alarm=_rate(sum(flag(r) for r in neg), len(neg)),
        negative_correct_approve=_rate(sum(r["verdict"] == "approve" for r in neg), len(neg)),
        category_recall_micro=_rate(tp, gtn),
        category_precision_micro=_rate(tp, prn),
    )


HEADLINE = ("verdict_accuracy", "positive_recall", "negative_false_alarm", "negative_correct_approve",
            "category_recall_micro", "category_precision_micro")


def bootstrap_ci(rows, n_boot=1000, seed=0, alpha=0.05):
    """Percentile bootstrap CIs, resampling positives and negatives separately (class counts stay fixed)."""
    rng = random.Random(seed)
    pos = [r for r in rows if r["label"] == "positive"]
    neg = [r for r in rows if r["label"] == "negative"]
    samples = {k: [] for k in HEADLINE}
    for _ in range(n_boot):
        s = [rng.choice(pos) for _ in pos] + [rng.choice(neg) for _ in neg]
        m = point_metrics(s)
        for k in HEADLINE:
            if m[k] is not None:
                samples[k].append(m[k])
    ci = {}
    for k, v in samples.items():
        if len(v) < max(10, n_boot // 2):
            ci[k] = None
            continue
        v.sort()
        ci[k] = [_r(v[int(alpha / 2 * len(v))]), _r(v[min(len(v) - 1, int((1 - alpha / 2) * len(v)))])]
    return ci


def score_rows(rows, expected_n=None, n_boot=1000, seed=0, scored=SCORED):
    """Full metric block. ``rows``: dicts with label (positive|negative), gt, verdict, pred, optional finish_reason/invalid_reason/usage.

    ``expected_n`` asserts the row count (a silently shrunken n is a bug, not a result).
    """
    if expected_n is not None and len(rows) != expected_n:
        raise ValueError("expected n=%d rows, got %d" % (expected_n, len(rows)))
    for r in rows:
        if r["label"] not in ("positive", "negative"):
            raise ValueError("bad label %r" % (r["label"],))
        if r["verdict"] not in VERDICTS + ("invalid",):
            raise ValueError("bad verdict %r" % (r["verdict"],))
    pos = [r for r in rows if r["label"] == "positive"]
    neg = [r for r in rows if r["label"] == "negative"]
    inv = [r for r in rows if r["verdict"] == "invalid"]
    m = point_metrics(rows)
    per = {}
    for c in scored:
        tp = sum(1 for r in rows if c in r["gt"] and c in r["pred"])
        fn = sum(1 for r in rows if c in r["gt"] and c not in r["pred"])
        fp = sum(1 for r in rows if c not in r["gt"] and c in r["pred"])
        per[c] = dict(gt=tp + fn, recall=_r(_rate(tp, tp + fn)), precision=_r(_rate(tp, tp + fp)))
    res = {k: _r(v) for k, v in m.items()}
    res.update(
        schema_version=SCHEMA_VERSION, n=len(rows), positives=len(pos), negatives=len(neg),
        n_invalid=len(inv), n_invalid_positive=sum(r["label"] == "positive" for r in inv),
        n_invalid_negative=sum(r["label"] == "negative" for r in inv),
        n_error=sum(r.get("invalid_reason") in ("error", "skipped") for r in inv),
        n_length_stop=sum(r.get("finish_reason") == "length" for r in rows),
        json_valid=_r(_rate(len(rows) - len(inv), len(rows))),
        always_flag_accuracy=_r(_rate(len(pos), len(rows))),
        ci95=bootstrap_ci(rows, n_boot=n_boot, seed=seed) if pos and neg else None,
        ci_method="stratified percentile bootstrap, %d resamples, seed %d" % (n_boot, seed),
        per_category=per)
    return res


def mcnemar_exact(correct_a, correct_b):
    """Two-sided exact McNemar p-value on paired per-row correctness vectors (same row order). Returns (b, c, p)."""
    if len(correct_a) != len(correct_b):
        raise ValueError("paired vectors differ in length")
    b = sum(1 for x, y in zip(correct_a, correct_b) if x and not y)
    c = sum(1 for x, y in zip(correct_a, correct_b) if y and not x)
    n = b + c
    if n == 0:
        return b, c, 1.0
    from math import comb
    k = min(b, c)
    p = sum(comb(n, i) for i in range(0, k + 1)) / 2 ** n * 2
    return b, c, min(1.0, p)


def paired_bootstrap_diff(rows_a, rows_b, metric="verdict_accuracy", n_boot=1000, seed=0):
    """CI of metric(A) - metric(B) over the same plugins (rows aligned by index). Returns (diff, lo, hi)."""
    if len(rows_a) != len(rows_b):
        raise ValueError("paired rows differ in length")
    rng = random.Random(seed)
    idx_pos = [i for i, r in enumerate(rows_a) if r["label"] == "positive"]
    idx_neg = [i for i, r in enumerate(rows_a) if r["label"] == "negative"]
    d0 = point_metrics(rows_a)[metric], point_metrics(rows_b)[metric]
    diffs = []
    for _ in range(n_boot):
        ix = [rng.choice(idx_pos) for _ in idx_pos] + [rng.choice(idx_neg) for _ in idx_neg]
        a, b = point_metrics([rows_a[i] for i in ix])[metric], point_metrics([rows_b[i] for i in ix])[metric]
        if a is not None and b is not None:
            diffs.append(a - b)
    diffs.sort()
    if d0[0] is None or d0[1] is None or not diffs:
        return None, None, None
    return _r(d0[0] - d0[1]), _r(diffs[int(0.025 * len(diffs))]), _r(diffs[min(len(diffs) - 1, int(0.975 * len(diffs)))])
