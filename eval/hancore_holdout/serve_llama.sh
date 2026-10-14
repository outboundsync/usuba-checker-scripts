#!/usr/bin/env bash
# Start llama-server for the HANCORE / Dell exam (run_eval.py --backend openai --base-url http://127.0.0.1:${PORT:-8080}/v1).
# Context math: llama-server -c is TOTAL context, split evenly across -np slots.
#   Exam prompts are ~6.7k-8k tokens, plus up to 2048 output tokens -> ~10k per request; 32k per slot leaves headroom.
#   Default: CTX_PER_SLOT=32768 x PARALLEL=4 -> -c 131072, -ngl 99.
#   2026-10-14 failure: -c 16384 with 4 slots = 4k per slot -> 1002/1054 requests "Context size has been exceeded".
# Usage: serve_llama.sh MODEL.gguf [extra llama-server args]   (env: CTX_PER_SLOT, PARALLEL, NGL, PORT, LLAMA_SERVER, ALLOW_SMALL_CTX=1)
set -euo pipefail
MODEL=${1:?usage: serve_llama.sh MODEL.gguf [extra args]}; shift
CTX_PER_SLOT=${CTX_PER_SLOT:-32768}; PARALLEL=${PARALLEL:-4}; NGL=${NGL:-99}; PORT=${PORT:-8080}
MIN=32768
for a in "$@"; do case "$a" in -c|--ctx-size|-np|--parallel) echo "ERROR: set CTX_PER_SLOT / PARALLEL env instead of passing $a (total -c is computed)." >&2; exit 1;; esac; done
if (( CTX_PER_SLOT < MIN )) && [[ "${ALLOW_SMALL_CTX:-0}" != 1 ]]; then
  echo "ERROR: CTX_PER_SLOT=$CTX_PER_SLOT < $MIN. Exam prompts (~6.7k-8k tokens + output) will overflow ('Context size has been exceeded')." >&2
  echo "       Set ALLOW_SMALL_CTX=1 only if you know the prompts fit." >&2; exit 1
fi
TOTAL=$(( CTX_PER_SLOT * PARALLEL ))
echo "llama-server: -c $TOTAL (${CTX_PER_SLOT}/slot x $PARALLEL slots), -ngl $NGL, port $PORT" >&2
exec "${LLAMA_SERVER:-llama-server}" -m "$MODEL" -c "$TOTAL" -np "$PARALLEL" -ngl "$NGL" --jinja --port "$PORT" "$@"
