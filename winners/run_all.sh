#!/usr/bin/env bash
# Reproduce the winners study. No GPU, no network, no LLM, $0. Needs /workspace/{sweep_repos,wt-retrain-v2} (method: the models repo docs/winners.md).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=${OUT:-/workspace/usuba-runs/winners}; mkdir -p "$OUT/cr2"
# the former branch checker-rules-v2 no longer exists; its tip is this repo's commit 8754bc4 (identical functest files). Override with CHECKER_V2_REF.
cd "${SCRIPTS_REPO:-$HERE/..}"
git archive "${CHECKER_V2_REF:-8754bc4d8900814697f7fc951b3b8521a77b17eb}" functest hancore | tar -x -C "$OUT/cr2"
cd "$OUT"
cp "$HERE"/{profile.py,run_checker.py,compare.py,overlap.py} .
python3 profile.py winners                 # -> winners_profile.json
python3 profile.py corpus                  # -> corpus_profile.json (5522 plugins from dell/sweep/corpus.jsonl, ~3 min)
python3 compare.py                         # -> comparison.md
(cd cr2/functest && python3 ../../run_checker.py)   # -> checker_results.json
python3 overlap.py                         # id-only overlap
