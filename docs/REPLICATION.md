# Replication guide: usuba-checker-scripts

What you can reproduce from this repository alone, and what needs inputs that are not published.

## 1. The Checker (fully reproducible)
1. `git clone` this repository, Python 3.10+.
2. Static checks need nothing else: `python3 functest/functest.py <plugin dir> --reasons`.
3. Runtime checks: install `quickshell` (0.3.x) and `sway`, then run the same command. The reference shell tree is `dell-ref/omarchy-4.0.4/` (override with `FT_DELL_FULL`).
4. Unit tests: `python3 -m pytest -q`. `functest/tests/test_dell_learned.py` skips two tests that need private sweep tooling.
5. `functest/STANDARD.md` is generated: `cd functest && python3 -m usuba.rules > STANDARD.md` (a test checks it is in sync).

Reference binary lists: `functest/dell_env/omarchy_bins.txt` is exactly the `bin/` listing of `dell-ref/omarchy-4.0.4/` (a test enforces it) and `system_bins.txt` is a generic list of stock Arch/Omarchy executables; the USB-B01/B05 rules need them, so they are kept.
Calibration (`functest/calibrate.py`): set `FT_CALIB_REPOS` to a directory of fetched good plugins (see section 2) and optionally `FT_CALIB_BAD` to your own known-bad plugin dirs; missing ones are skipped.

## 2. Third-party plugin sources
Plugin source trees are **not** stored here. Repos used as test subjects or data sources are pinned by URL + commit SHA in the sibling repository
(`usuba-checker-models`, file `sources/plugin_sources.json`, only repos whose pinned commit has an MIT/Apache/ISC/BSD LICENSE file) and fetched with
`sources/fetch_plugin_sources.py`. Trees without a permissive LICENSE file are not redistributed and not listed.

## 3. Mining pipelines
- `hancore/fetch.py` re-downloads the public marketplace review threads (needs a GitHub token in `GH_TOKEN`; the downloaded text is **not** redistributed, thread URLs are the source of truth). `hancore/measure_*.py` then recompute `hancore/rule_metrics.json`.
- `train/version_history/01..05_*.py` and `jankeesvw-history/scripts/01..10_*.py`: bug-fix history mining, run in numeric order. They clone public repos and call the Checker; LLM judging steps use an OpenAI-compatible endpoint configured by env vars (`OPENROUTER_API_KEY`), cached verdicts are not published.
- `winners/run_all.sh`: Checker profile of the marketplace winners.

## 4. Evaluation harness
`eval/hancore_holdout/run_eval.py` (+ `serve_llama.sh` for a local GGUF with 32k context per slot) scores a model on the sealed holdout. The holdout manifest is private;
ids and the SHA-256 of the manifest are in `eval/hancore_holdout/`. To use your own holdout, produce a `manifest.jsonl` with the same fields and run `select.py`/`run_eval.py` against it.

## 5. What is not reproducible from public material, and why
| Item | Reason |
|---|---|
| Hardware-verified answer key and labels for real-device runs | Private by decision; the Checker is validated against it internally only |
| Device run output, screenshots, device captures | Private (contains hardware and path details) |
| Raw review text | Written by other people, no licence; re-fetch from the thread URLs |
| Sealed holdout contents | Kept sealed to prevent contamination; ids and hash published |
| Raw outputs of proprietary models | Not redistributed; only score tables are published (in the models repository) |
| Plugin trees without permissive LICENSE | All rights reserved by default |

Scripts that read the private inputs (for example `functest/rescore.py`, `calibrate.py`, `eval/dellkey/*`) are published as code only and will report missing files unless you supply equivalent inputs.
