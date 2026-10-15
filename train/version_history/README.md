# Version-history bug-fix mining (Usuba Checker)

Full method, counts, license notes and learnings: `docs/version-history.md` in the repo (branch `version-history`, dir `train/version_history/` for scripts). This directory is the run output.

Files (data/): `universe.json` (5,149 repos + exclusions), `clone_status.jsonl`, `repo_commit_counts.json`, `candidates.jsonl` (all 50,676 mechanically verified fix-message hunks), `candidates_dedup.jsonl` (1,400 sampled for LLM judging), `llm_verdicts.jsonl`, **`verified_pairs.jsonl` (669 verified pairs)**, `summary.json`, `sample10.txt`.
`candidates_partial_uncapped.jsonl` is an abandoned first mining pass (no per-repo cap); superseded, not copied to the store.

Headline: 5,128 repos cloned with full history (4,930 with >1 commit); 12,109 candidate fix commits (50,676 hunks); 1,400 judged; 669 verified pairs in 556 repos; 1,338 potential training rows (669 broken + 669 approve).
Excluded: the 116 Dell ground-truth plugin ids (ids only; labels never read), the 329 hancore_holdout repos, and jankeesvw repos.
