# Checker uplift experiment (plan, 2026-10-13)

Question: how much does Usuba Checker feedback raise *hand-checked* passes on the 49 clean holdout prompts, for frontier and low-end models?

## Arms
- Frontier: gpt-5.6-sol, claude-opus-5.5, claude-sonnet-5.5, gemini-3.1-pro-preview, grok-4.3.
- Low-end/open: stock 7B and 14B (local, vLLM on the box GPU if available, otherwise the existing gen files + an OpenRouter equivalent), qwen/qwen3.6-27b, qwen3-coder, kimi-k3, deepseek-v4-pro-0813.

## Procedure (runs/fixer/loop.py, generalised)
1. Round 0 reuses the existing generations (runs/smoke-2026-10-11, runs/w2, runs/fixer/base). That costs nothing and keeps "before" identical to the scoreboard.
2. For each failing row, send the model its own answer plus only the Checker output: rule-id reasons and fix hints from rescore.score_row `reasons`, plus runtime errors. Never send reference answers. Run up to 3 fix rounds and stop at the first pass.
3. Settings: temperature 0, max_tokens 16000, reasoning low. OpenRouter body gets `provider: {zdr: true, data_collection: "deny"}` (loop.py currently only sets `sort`, so this must be added). The key is read from env and never printed.
4. Grade every round with the merged Usuba Checker. Truncations and loops count as fails.
5. Hand-check all Checker passes, before and after, with the runs/fixer/hc.py rubric (firm / lenient). Report hand passes at r0 and r3 per model, plus Checker passes per round.

## Budget ($30 OpenRouter cap)
- Measured: qwen3.6-27b costs about $2.2 for 49 prompts × up to 4 rounds.
- Only failing rows get fix rounds, so expect 30–45 rows per model.
- Estimates: open models (27b, qwen3-coder, kimi, deepseek) about $1–3 each, about $8 total. Frontier: Sonnet/Gemini/Grok about $3–5 each; GPT-5.6/Opus about $6–10 each.
- Order: open models first, then Sonnet, Gemini and Grok, then GPT-5.6 and Opus while budget remains. A running cost tally in loop.py (usage.cost) hard-stops at $29.
- 7B/14B: local inference if a GPU is present (free); otherwise skip them or use the cheapest hosted equivalent.

## Concurrency
At most 6 grader/Quickshell processes in total (15 GB box). Generation is network-bound and runs with 8 threads; grading uses J≤4 while nothing else runs.
