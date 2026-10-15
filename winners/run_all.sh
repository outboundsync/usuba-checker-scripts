#!/usr/bin/env bash
# Reproduce the winners study. No GPU, no network, no LLM, $0. Needs /workspace/{sweep_repos,wt-retrain-v2} (see README in docs/winners.md).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=${OUT:-/workspace/usuba-runs/winners}; mkdir -p "$OUT/cr2"
cd /workspace/wt-retrain-v2
git archive checker-rules-v2 functest hancore | tar -x -C "$OUT/cr2"      # checker at branch checker-rules-v2 (57018c8)
cd "$OUT"
cp "$HERE"/{profile.py,run_checker.py,compare.py,overlap.py} .
python3 profile.py winners                 # -> winners_profile.json
python3 profile.py corpus                  # -> corpus_profile.json (5522 plugins from dell/sweep/corpus.jsonl, ~3 min)
python3 compare.py                         # -> comparison.md
(cd cr2/functest && python3 ../../run_checker.py)   # -> checker_results.json
python3 overlap.py                         # id-only overlap
