# Version-history bug-fix mining

Goal: (buggy version, fixed version, fix diff) pairs from plugin git history, with file:line in the PRE-fix version, a bug-kind label and the fix. Run date 2026-10-15. Outputs: `/workspace/usuba-runs/version-history/` and store `usuba-v2distill/version-history/`.

## Replicate (exact commands, from repo root `train/version_history/`, outputs go to `data/` under cwd)
```
mkdir -p data && python3 01_build_universe.py      # reads corpus.jsonl, registry_repos/*/.git remotes, holdout plugin_ids.txt, and ONLY the 'id' field of dell_ground_truth.jsonl
python3 02_clone_history.py       # git clone --bare --filter=blob:none --single-branch, 24 threads, 120 s timeout -> /workspace/vh_repos (~5,146 ok)
python3 03_mine_candidates.py     # 8 threads; MAXCAND=120 fix-message commits/repo; skips jankeesvw
MAXC=1400 python3 03b_prefilter.py   # deterministic, random.seed(0)
BUDGET=6.0 python3 04_llm_verify.py  # needs OPENROUTER_API_KEY in env (never logged)
python3 05_report.py              # verified_pairs.jsonl, summary.json
```
Inputs: `wt-retrain-v2/dell/sweep/corpus.jsonl` (5,679 rows; 5,523 plugins), `/workspace/registry_repos` (731 repos, all shallow depth-1), `/workspace/sweep_repos` (only 875 of 4,943 kept .git, all shallow), `wt-v3-prep/eval/hancore_holdout/plugin_ids.txt`. None of the on-box repos had history (all depth 1), so history was fetched from the GitHub URLs (blobless full-history clones; blobs fetched lazily on diff). No credentials used.

Model: `qwen/qwen3.5-397b-a17b` via OpenRouter (open weights), temperature 0, reasoning disabled, JSON output, max_tokens 350, 32 threads. Cost: 1,400 judgments = $2.89 (+$0.02 smoke test), budget cap $8. No GPU, no Dell, no push.

## Method
1. Universe: 5,149 repos after excluding 299 holdout repos (of the 329 ids, 299 appear in corpus) and 75 repo urls tied to the 116 Dell ground-truth ids (by plugin_id/dell_name/registry dir).
2. Candidates: non-merge commits whose subject/body matches fix/bug/crash/error/broken/regression/hang/fail/wrong/leak/race/null/... and not docs/chore/style/refactor/feat/test/ci/release/bump prefixes; touching 1-3 code files with <=60 changed lines; hunks <=24 lines.
3. Mechanical verification: for every hunk, `git show parent:file` line(s) at the diff's old line number must equal the removed text exactly (pure insertions: anchor = line after insertion point, must exist).
4. Prefilter for LLM budget: strong keyword in the subject, hunk <=16 lines, non-comment change, max 8 commits/repo, shuffled (seed 0), first 1,400.
5. LLM judge sees commit message, numbered pre-fix excerpt, hunk; returns is_functional_bug_fix, reject reason, defect_line, bug_kind, defect, fix, confidence. Verified = judge true AND confidence>=0.7 AND defect_line within [pre_line-1, pre_end+1] AND mechanical check passed.

## Counts
| Step | Count |
|---|---|
| Repos in universe / cloned with full history | 5,149 / 5,128 (4,930 with >1 commit) |
| Candidate fix commits (message match + small code diff + mechanical line match) | 12,109 commits, 50,676 hunks, 2,633 repos |
| Judged by LLM (sampled) | 1,400 |
| Rejected: cosmetic 141, unclear 176, feature 82, refactor 49, config-tweak 27, docs 19, other 1 | 495 |
| Failed line/confidence gate | 236 |
| **Verified pairs** | **669 (669 commits, 556 repos)** |

Verified yield 669/1,400 = 48%; the 12,109-commit pool was not fully judged, so the full pool could plausibly give several thousand more (extrapolation only, untested; the prefilter dropped ~18k hunks before judging).

Per bug kind: wrong-condition-or-logic 178, ui-layout-or-state 127, api-compat-change 54, race-or-timing 48, security 46, process-or-resource-lifecycle 46, wrong-path-or-command 44, env-or-config-assumption 35, error-handling 28, syntax-or-parse-error 24, missing-dependency-or-install 15, shell-quoting-or-expansion 12, null-or-missing-guard 11, other 1.

Sample pairs: `data/sample10.txt` (10, seed 0, confidence>=0.9).

## Training-row potential
669 broken rows (pre-fix version, exact file:line) + 669 approve rows (post-fix version) = up to 1,338. Use caution:
- 538 pairs have removed lines (511 where the judged defect line is exactly a removed line: strongest). 131 are pure insertions (missing guard/flag): line is an anchor, not the defect text; weaker for exact-line grading.
- Approve rows: post-fix is only "fixed for this defect"; it may contain other bugs, and the plugin has no runtime check. Treat as lower-confidence approve; prefer plugins whose latest HEAD passed the existing functest if reused.
- Label quality rests on one LLM judge plus mechanical line checks; no second reviewer. Spot-check before training.
- Dedup against eval: holdout/Dell repos excluded entirely, but same-author forks may overlap; run the existing dupes check.

## Licenses
Detected from LICENSE at HEAD of each verified repo: MIT 632, GPL 22, Apache-2.0 8, BSD 2, ISC 1, unrecognised license file 2, none found 2 (rows). Rows from GPL repos (copyleft; derivative training-data implications unsettled), unlicensed repos (all rights reserved) and unrecognised licenses should be held out of any released dataset; MIT/Apache/BSD/ISC require retaining copyright notice, so keep `url`+`commit` provenance fields (included). License at HEAD may differ from license at the fixed commit.

## Learnings
- On-box repos are depth-1; history must be fetched. Blobless clones of 5k repos took ~25 min; blob-lazy diffing was the bottleneck (mining ~1 h, a few huge repos block ordered output; hence MAXCAND cap).
- Subject keyword "fix" is a weak signal: ~52% of strongly-keyworded small commits were cosmetic/feature/unclear.
- QML binding/attached-property bugs and wrong-condition logic dominate; shell-quoting and null guards are rare.
- Judge-labelled defect line differs from hunk start in some cases; the +-1 gate removed many (236).
