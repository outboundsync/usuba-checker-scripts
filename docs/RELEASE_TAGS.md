# Release and exam tag plan (audit F5)

Harris decides when to cut tags; tags are cheap to add and, once pushed, should never be moved (we never force-push).

## Released
| Tag | Release | Date | Notes |
|---|---|---|---|
| `checker-v0.1.0` | Usuba Checker Scripts v0.1.0 | 2026-10-17 | Enforces Usuba Standard v0.2 (66 rules). Static checks run on any machine; the runtime stage needs the reference build. Sibling: `model-v0.1.0` in `usuba-checker-models`. |

## Naming
| Tag | Meaning | Applied to |
|---|---|---|
| `checker-vMAJOR.MINOR.PATCH` | A Usuba Checker Scripts release (matches `pyproject.toml` `version`) | scripts |
| `exam-<name>-YYYY-MM-DD` (e.g. `exam-v1-2026-10-14`) | The code that scored a published exam run | scripts (scorer) **and** models (prompt, code_blob) at the same date |
| `data-rN` (e.g. `data-r4`, `data-r5`) | A training-set build; points at the models commit that holds the builders + GATE_REPORT | models |
| `model-<run-name>` (e.g. `model-usuba-9b-v1-q4km`) | A trained artefact whose weights sha256 is recorded in the repo | models |

## Procedure (when approved)
1. `main` must be green: tests, ruff, `tools/scan_public.py`, gitleaks, `tools/derive_provenance.py --check`.
2. Annotated tag, message lists the sibling repo's pinned SHA: `git tag -a exam-v1-2026-10-14 <sha> -m "scripts <sha>; models <sha>; checker rules_hash <hash>"`.
3. Push the single tag by name (`git push origin exam-v1-2026-10-14`), never `--tags`.
4. Result files written from now on carry `checker_git_sha`, `checker_git_dirty`, `rules_hash` (`functest/usuba/provenance.py`); refuse to tag if
   `checker_git_dirty` is true in any result you cite.

## Candidate tags for existing history (proposal only; verify before tagging)
Derived by `tools/derive_provenance.py` into `provenance/ARTIFACTS.json`. The v1/v2 exam numbers in the models README were produced before
write-time provenance existed, so a tag on them can only say "code as of commit X" (an upper bound; see `confidence` in that file).

| Proposed tag | Repo | Commit | Basis |
|---|---|---|---|
| `exam-v1-2026-10-14` | scripts | `9cf0461` (last change to `eval/hancore_holdout/run_eval.py` on or before 2026-10-14) | `git log --until='2026-10-14 23:59:59 -0600' -1 -- eval/hancore_holdout/run_eval.py` |
| `data-r4` | models | `29e1f9c` ("r4 final") | commit message |
| `audit-A-2026-10-15` | both | tips after stream A merges | audit baseline for this review |

## Older committed artefacts
`functest/results.json`, `functest/recal_registry.jsonl`, `winners/checker_results.json` and `results/hitcheck/*` have no write-time Checker Scripts SHA.
`provenance/ARTIFACTS.json` records sha256 plus the bracketing commits; files touched by more than one commit are flagged as possibly mixing
Checker Scripts versions. The only way to get an exact SHA for those is to re-run them with the current Checker Scripts (which now stamps itself).

`jankeesvw-history/v3fixes_wip_snapshot.sha256` is the hash list of a WIP tree. It cannot verify against HEAD (the files moved on, two live in
the models repo). `provenance/SNAPSHOT_V3FIXES.json` resolves every listed hash to the exact commit holding that blob (19/19 resolved).
