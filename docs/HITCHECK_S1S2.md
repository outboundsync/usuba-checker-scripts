# Hardware-derived S1 / S2 drafts (Janus, 2026-10-15) - PROVISIONAL, EVAL-ONLY

Never train on anything listed in `results/s1s2/*_exclude_from_training.txt`. Hardware labels come from the Dell (truth); the judge panel and the auto checklist are provisional aids, not labels.

## Pipeline
1. `tools/hitcheck/sandbox_probe.sh` proves the sandbox first (`docs/SANDBOX_PROOF.md`): 46 BLOCKED, 12 INFO, 0 LEAK on the Dell; a hostile plugin trying ~/.ssh, host sockets, env, /dev, network, symlink/FIFO evidence poisoning failed on every attempt.
2. `build_s2_package.py` selects S2 candidates; `run_hitcheck.sh` runs them (bwrap, `OBSERVE=1` host-side observer); `checklist.py` makes the auto verdict and the review sheet; `build_s1_hw.py` builds S1 hardware labels; `guard_recheck.py` re-applies the current holdout guard (repo, manifest id, content, per-file Jaccard, same-name, same-author vs sealed holdout + Dell key).

## Counts (after the current guard)
- S2: 267 selected -> 46 dropped by the new guard -> **221 run on hardware; 220 works, 1 unsure (dependency)**. Auto verdict: 169 PASS_AUTO, 51 REVIEW, 1 FAIL. Human spot-check set: **81** (all REVIEW + seeded 10% of PASS_AUTO). Nobody has hand-reviewed them: they are candidates, not a clean set yet. `human_verdict` columns in `review_sheet.csv` are empty.
- S1 hardware-observable: 912 -> 185 plugins dropped by the guard -> **666 items**. LOAD group: real_hw 22, warn_hw 55, no_symptom_hw 150 (Checker Scripts FAIL on a plugin that works = false alarm). BIN group: present_hw 100, absent_hw 304 (real candidates), unresolved 35. 614 finding categories are not hardware-observable and are excluded.
- Screenshots of the opened surfaces stay on the Dell (`~/usuba-janus/s2-run/results/raw/*/obs`); they are not in the repo.

## Caveats
- The checklist ignores the runner's own `inotifywait` watcher when flagging leaked processes.
- Wayland socket is passed into the sandbox; plugin windows flash on the live desktop during a run.
- Binary extraction for S1 BIN findings is noisy; `absent_hw` means "candidate real", needs the adjudication.
