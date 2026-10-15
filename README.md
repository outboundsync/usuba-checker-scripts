# usuba-checker-scripts

The **Usuba Checker** decides whether an [Omarchy](https://omarchy.org) shell plugin actually works. It is plain Python, not AI: deterministic static
checks plus a real headless run of the plugin inside a reference Omarchy 4.0.4 / Quickshell environment. The same plugin always gets the same verdict.
Every failure carries a rule id from the Usuba Standard ([`functest/STANDARD.md`](functest/STANDARD.md)), so a report can be read by a person or handed
to a reviewer model.

This repository holds everything that **decides, mines, builds data from, or measures**. The code that **trains and ships the reviewer model**, the data policy,
exam results and model card are in the sibling repository `outboundsync/usuba-checker-models`.

## Run it
```sh
python3 functest/functest.py <plugin dir>             # full JSON report
python3 functest/functest.py <plugin dir> --reasons   # PASS/FAIL plus one line per rule hit
```
Python 3.10+, standard library only. The runtime stage needs `quickshell` and a headless Wayland compositor (`sway`) on `PATH`; `qmllint` is used by some checks.
Without them the static checks still run and the runtime stage says why it could not start.

## Layout
| Path | What it is |
|---|---|
| `functest/functest.py` | Entry point: static checks + runtime, one verdict |
| `functest/static_checks.py`, `functest/usuba/` | Manifest/layout/QML/JS checks and the hardening rules (`rules.py` is the single source of rule ids; `types.json` the QML type table) |
| `functest/dell_checks.py`, `functest/dell_learned.py`, `functest/dell_env/` | Checks and sandbox derived from a real Omarchy 4.0.4 install. The `dell_` prefix is a historical name for "the reference Omarchy laptop"; it was kept so imports and history stay stable. |
| `functest/runtime.py` | Headless Quickshell run against the reference shell |
| `functest/fixtures/hyprland-0.56.2/` | Sanitised `hyprctl` reply shapes replayed by the fake `hyprctl` (placeholder monitor/device/window names) |
| `dell-ref/omarchy-4.0.4/` | `/usr/share/omarchy` from Omarchy 4.0.4-1 (basecamp/omarchy, MIT) used as the reference tree |
| `validator/` | Earlier standalone validator port (`omarchy-plugin-validate`, qmllint wrapper) |
| `hancore/` | Scripts that mine public marketplace review threads into rule evidence (`rule_metrics.json`); re-fetch with `hancore/fetch.py` |
| `winners/`, `build_dataset*.py`, `tools_analyze.py`, `gen_docs.py` | Corpus analysis and dataset-building tools |
| `train/version_history/`, `jankeesvw-history/` | Bug-fix history mining pipelines (scripts, rules USB-JV01..09, metrics) |
| `eval/hancore_holdout/` | Exam harness (`run_eval.py`, `rescore.py`, `select.py`, `serve_llama.sh`); the sealed holdout is published as **ids + manifest hash only** |
| `eval/dellkey/` | Reason-grading harness and rubric (the answer key itself is private) |
| `tests/`, `functest/tests/` | Unit tests, CPU only |

## Test
```sh
python3 -m pip install pytest && python3 -m pytest -q
```

## What is deliberately not here
Private device run output, the hardware-verified answer key and labels, raw review text, the sealed holdout contents, raw outputs of proprietary models, and
third-party plugin source trees without a permissive LICENSE file. Hit-check on real hardware: [`docs/DELL_HITCHECK.md`](docs/DELL_HITCHECK.md) (results in `results/hitcheck/`, tooling in `tools/hitcheck/`). See [`docs/REPLICATION.md`](docs/REPLICATION.md) for what that means for replication and
how to rebuild the corpora from public sources.

## Licence
Code: MIT (see `LICENSE`). Third-party material keeps its own licence: `dell-ref/` and `validator/OMARCHY-LICENSE` are from basecamp/omarchy (MIT); see `NOTICE`.
