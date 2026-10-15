# Sealed HANCORE holdout (ids and hash only)

The exam set has 329 public marketplace plugins with reviewer findings. To keep it usable as a contamination check, only these are published:

- `plugin_ids.txt`: the 329 plugin repository URLs (the exclusion list every training-data builder must respect).
- `MANIFEST.sha256`: SHA-256 of the private `manifest.jsonl` (labels, findings, pinned commits). Whoever holds the manifest can prove it is the one the published
  numbers were computed on; nobody else can read the answers.

The manifest, the plugin archives and the raw per-plugin results stay private (`.gitignore` blocks them). Score tables are in `outboundsync/usuba-checker-models`.
The harness (`run_eval.py`, `rescore.py`, `select.py`, `serve_llama.sh`) is here; it needs the private manifest to run an exam. `select.py` documents how the set was drawn.
