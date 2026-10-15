# jankeesvw history mining (docs/jankeesvw-history.md)

Deep pass through the full commit history of 19 of jankeesvw's plugin repos: classify every commit, verify the pre-fix line of every bug fix, run the Checker on the pre-fix trees, extract lessons, build candidate training rows (source=`jankeesvw-history`, MIT, `NOTICE`). Outputs live in `/workspace/usuba-runs/jankeesvw-history/` (REPORT.md first) and are copied to `/cursor/stores/store-59a6dbfe-4592-4709-aa00-b03118ea5a20/usuba-v2distill/jankeesvw-history/`.

## Rules followed
No GPU, no Dell commands, no deletions, no pushes. Excluded entirely (never read): `jankeesvw/omarchy-clippy` (HANCORE holdout), `jankeesvw/omarchy-time-machine` (existing holdout). `functest/dell_ground_truth.jsonl` and `eval/hancore_holdout` were not read. LLM: `qwen/qwen3.5-397b-a17b` through OpenRouter only (`reasoning: {enabled: false}`, `temperature: 0`, `response_format: json_object`, `OPENROUTER_API_KEY` from the environment, never printed), about $2 of a $5 budget.

## Inputs
- Clones: `/workspace/ref/jankeesvw/<repo>` (21 repos; `omarchy-meeting-recorder` was shallow: `git -C /workspace/ref/jankeesvw/omarchy-meeting-recorder fetch --unshallow`, 58 commits).
- Checker snapshots (committed state, never the dirty worktrees):
  ```
  cd /workspace/wt-v3-fixes
  mkdir -p /tmp/jh_snap/v2 /tmp/jh_snap/v3fixes /tmp/jh_snap/v3fixes-head
  git archive checker-rules-v2 functest train | tar -x -C /tmp/jh_snap/v2            # 57018c8
  git archive 763fe65          functest train | tar -x -C /tmp/jh_snap/v3fixes       # v3 prep; identical findings to v2 on this data
  git archive d00fcc0          functest train | tar -x -C /tmp/jh_snap/v3fixes-head  # v3-fixes HEAD at run time (prompt_v3, checker_report, lifecycle rules, HC rename)
  ```
  (the archives contain `functest/dell_ground_truth.jsonl`; nothing here reads it).
- Prompt/schema: `train/prompt_v3.py` @d00fcc0 (7-shot prefix, `P.messages`), `train/checker_report.report` @d00fcc0, row fields identical to `/workspace/usuba-runs/v3-fixes/synthetic_rows.jsonl`; tokenizer `~/.cache/huggingface/hub/models--Qwen--Qwen3.5-9B/.../tokenizer.json`, ceiling 32000 tokens (train max_len 32768).

## Commands (run in order from `/workspace/usuba-runs/jankeesvw-history`, scripts in `scripts/`)
```
python3 scripts/01_inventory.py                      # data/commits.jsonl: all refs, merges, numstat, binary flags
BUDGET=3 WALL=600 python3 scripts/02_classify.py     # data/classified.jsonl: qwen3.5-397b, class + defect line + category + fix pattern + origin per commit (rerun until no new lines; 1 commit needed a manual override, see 03)
python3 scripts/03_verify.py                         # data/bugs.jsonl, data/classes.jsonl: mechanical pre-fix line verification (removed / adjacent), blame links
BUDGET=1.5 python3 scripts/04_review.py              # data/review.jsonl: skeptical second pass + plain-words description (qwen3.5-397b)
python3 scripts/05_run_checker.py                    # data/checker_runs.jsonl: v2, v3fixes_763fe65, v3fixes_d00fcc0 on pre and post trees (scripts/checker_worker.py)
python3 scripts/06_merge.py                          # data/bugs_final.jsonl, data/summary.json (HIT/COINCIDENT/FILE/MISS)
python3 scripts/07_build_rows.py                     # rows.jsonl, rows_tierB.jsonl, rows_extra.jsonl, data/rows_stats.json
python3 scripts/08_validate.py                       # schema, prompt prefix, cited line == pre-fix line, tokens, exclusions
python3 scripts/10_measure_rules.py                  # data/jv_rules_metrics.json for scripts/jv_rules.py (USB-JV01..09)
python3 scripts/09_report.py                         # REPORT.md, bugs.tsv, commits_all.jsonl, NOTICE (lessons text: scripts/lessons.md)
```
`07` and `10` expect git-archive trees under `/tmp/jh_trees/<repo>_<sha10>_{pre,post}` (`05` creates them) and the snapshot dirs above. `jankeesvw-history/scripts/` in this branch is a copy of those scripts; `data/` is not committed (large; see the store copy).

## Method notes
- Defect line: the model cites a PRE-fix line number and quotes the text; `03_verify.py` accepts it only if `git show <parent>:<file>` line N equals the quote and N is a line the diff removes/changes (`removed`) or a context line within 3 lines of an insertion (`adjacent`). A quote that matches exactly one removed line re-anchors the number.
- A second pass (`04_review.py`) sees the pre-fix excerpt, the fix diff and the commits that last touched the lines (git blame) and answers: real defect on its own, tier A (functional/security) or B (cosmetic/UX), a better line, the plain-words description (no commit/review framing), symptom, root cause, kind, origin.
- Origin: `version_change` only for the two dated events (subject contains `Commons.Color` or `new Omarchy shell`); `fix_of_fix` only when blame shows the removed lines were last changed by an earlier bug-fix commit; `regression_in_recent_feature` when the reviewer says it follows an earlier commit that was not a fix.
- Checker outcome per bug: HIT = finding in the defect file within 5 lines whose rule category equals the bug category or that disappears after the fix; COINCIDENT/FILE/MISS otherwise. Layers: "prompt+enabled" (what `checker_report.report` shows plus enabled USB-H/HC) and "all-rules".
- Rows: broken = parent tree (text files only, `read_dir` rules, binary/image/audio extensions excluded, same `scrub` as v3), finding = exact `file:line` + description (<=300 chars, hygiene regex), `load` = `unsure` for security kind else `broken`; approve = commit tree, only when no later verified defect of the same repo is still present in it (weight 0.5). Selection: authored by Jankees van Woezik, real defect, code file, tier A in `rows.jsonl`; version-compat commits capped at 3 per event (rest in `rows_extra.jsonl`).
- `scripts/jv_rules.py` (USB-JV01..09) is not wired into `functest/`; to port, copy the module next to `lifecycle_rules.py` and call `jv_rules.check(files)` from `checker_report.report_and_warn_rules`. Recall is measured on the same history the rules were derived from (optimistic); JV07/JV08 are version-dependent and should stay experimental.

## Replication caveats
LLM answers are not bit-reproducible (temperature 0, but provider routing varies); raw answers are kept in `data/classified.jsonl` and `data/review.jsonl`, so `03`..`10` are deterministic given them. Checker snapshots live in `/tmp`; recreate them with the commands above.
