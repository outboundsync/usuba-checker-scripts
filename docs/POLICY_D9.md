# D9: two long-standing verdict pardons (decision needed)

The earlier reviews (`reviews/SYNTHESIS.md`) flagged two places where the Checker is more lenient than the rule text:

| Item | Where | Default (historical) | Strict (`FT_STRICT_D9=1`) |
|---|---|---|---|
| Zero-size pardon | `functest/functest.py::apply_zero_size_pardon` | "bar widget has zero size" / "draws nothing visible" becomes a **soft** note when the entry point has a conditional `visible:`/`width:`/`opacity:` line | stays an **error** (USB-R03) |
| "Binding loop detected" | `functest/runtime.py` (`SOFT_PAT`, `DOWNGRADE`) | soft warning | an **error** when the line is attributed to the plugin |

## Why it is a flag, not a change
Both pardons were calibrated against real Dell behaviour (plugins with these messages work on the device). Flipping the default would
change published verdicts, the Dell calibration results, and the labels already baked into r4/r5 training rows. So:

* the default is unchanged (no published number moves);
* `FT_STRICT_D9=1` turns both on together; the active policy is stamped in every report (`meta.policies.strict_d9`) and in the
  `rescore.py` cache key, so strict and default results can never be mixed silently;
* tests: `tests/test_policy_d9.py`.

## Decision for Harris
1. Keep default lenient (recommended until the Dell hit-check data say whether zero-size/binding-loop plugins really misbehave on hardware).
2. Or make strict the default for **new** data builds only (never re-label existing rows; record `strict_d9` in the row meta).
3. Or drop the pardons entirely (needs a Dell-key re-run first: `FT_STRICT_D9=1 python3 functest/rescore.py` on the 86-row Dell key and compare).
To measure the impact before deciding: run the Dell key and the holdout twice (default / strict) and diff `categories`.
