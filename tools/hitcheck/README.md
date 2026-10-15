# Usuba Dell hit-check package

Real-hardware check of the Checker rules and of version-history bug pairs. **User space only**: no sudo, no system changes, everything is written under `~/usuba-hitcheck`.
Nothing in this package was run on the Dell when it was built; it was dry-run on the build box (headless sway, Quickshell 0.3.2) with 16 plugins.

## What it does
Every plugin is loaded in its own Quickshell instance on your live Wayland session (same method as the earlier Dell sweeps, the earlier device sweep script (not published)): fake HOME with the plugin enabled,
copy of `/usr/share/omarchy/shell`, 24 s per plugin: load, `listPlugins` (s9), `toggle` (s10), the plugin's own safe no-argument IPC methods (s12, same allow/deny list as `dell/interact.sh`), `toggle` again (s18).
No keyboard or mouse input, no screenshots. Per plugin it records works/broken plus the error, and evidence for the rule defect (see below). One JSON line per plugin goes to a single file.

Safety (all inside the per-job sandbox, `bwrap`, no root needed):
- `/` read-only, your real `$HOME` hidden (empty tmpfs, only the per-job fake HOME is writable), `/tmp` is a private per-job directory (its content is listed as evidence).
- network off (`NET=1` turns it on), private runtime dir with only the Wayland socket (no dbus, pipewire, pulse, hyprland, systemd, ssh/gpg agent sockets), private pid namespace.
- `PATH` shims log and refuse: curl wget sudo pkexec doas su pip pipx npm npx cargo go uv yay paru pacman flatpak nc ssh scp rsync xdg-open systemctl dbus tools; `git clone/fetch/pull/push` refused, `hyprctl` refuses everything that changes state.
- 70 s hard timeout per plugin, 10 GB memory cap via `systemd-run --user --scope` if available, waits when MemAvailable < 1.5 GB, `touch ~/usuba-hitcheck/STOP` ends the run.
- Without `bwrap` the script refuses to run unless `ALLOW_NO_SANDBOX=1` (then plugins can write outside ~/usuba-hitcheck, e.g. /tmp).
- Shipped binaries (ELF) were removed from the plugin trees; plugins that need them end as `unsure (dependency)`.

## Contents
| file | what |
|---|---|
| `run_hitcheck.sh` | the one run script (`--preflight`, `A`, `B`, `all`) |
| `hc_signal.py` | helper called by the run script: run directory -> one JSON line |
| `plugins-A.tar.gz`, `plugins-B.tar.gz` | plugin sources (Batch A rule samples, Batch B pre/post trees) |
| `jobs.tsv`, `jobs.json` | job list (id, kinds) and the metadata (rule claims, pair info) |
| `analyze_results.py` | turns the returned JSONL into the tables (run on the box, not the Dell) |
| `SHA256SUMS` | checksums |

Batch A: 276 plugin loads + 8 synthetic = 284 jobs: 13 enabled rules of branch v3-fixes (USB-HC01, 02, 04, 05, 08, 09, 10, 15, 16, 17, 19, 20, 25) with about 20 plugins each whose hit still fires under the current code (prepared samples first, topped up with a fixed seed),
lifecycle rules USB-L02 (7), USB-L03 (1 synthetic), USB-N01 (2 synthetic), USB-N02 (1 synthetic), 37 skip-rule cases (the old rule fired, the v3-fixes skip conditions now suppress it; includes the winners report cases: radio-atlas, omapods, github, omagotchi), 4 clean synthetic controls.
Batch B: 30 version-history pairs (60 jobs, `-pre` = parent commit, `-post` = fix commit), MIT only, 12 bug kinds, QML files, excluding the Dell key ids/trees, hancore_holdout and jankeesvw repos.

## Steps on the Dell
Open a terminal **inside the desktop session** (the script needs the Wayland socket; not over plain ssh).
```sh
mkdir -p ~/usuba-hitcheck/pkg
# copy this whole folder to ~/usuba-hitcheck/pkg/  (for example: scp -r <build-box>:<package dir>/. <device>:~/usuba-hitcheck/pkg/)
cd ~/usuba-hitcheck/pkg && sha256sum -c SHA256SUMS
./run_hitcheck.sh --preflight          # must end without FAIL; "warn" lines are explained in the output
ONLY=a-syn.ok.panel-open-close,b01-meviusisback__keybinds-plugin-pre,b01-meviusisback__keybinds-plugin-post ./run_hitcheck.sh all   # 3-job smoke test, about 40 s
rm ~/usuba-hitcheck/results/hitcheck-results.jsonl   # drop the smoke lines (or keep them: re-runs overwrite by job name in the analysis)
./run_hitcheck.sh all                  # everything: 344 jobs; P=3 default (P=2 if the machine is busy)
```
Batch only: `./run_hitcheck.sh A` or `./run_hitcheck.sh B`. The run is resumable: finished jobs (lines in the JSONL) are skipped. Stop early with `touch ~/usuba-hitcheck/STOP`.
Expected runtime: about 28 s per plugin wall time on the build box; with P=3 about 55-70 min for all 344 jobs (A about 50-60 min, B about 10 min). Disk: raw per-job logs about 2 MB per 16 jobs (~45 MB total), plus 55 MB sources.

Return only this file to the box: `~/usuba-hitcheck/results/hitcheck-results.jsonl` (about 1.5 MB; plugin evidence and paths under ~/usuba-hitcheck only). `~/usuba-hitcheck/results/raw/<job>/` keeps the raw logs for a plugin you want to look at.

Clean up afterwards: `rm -rf ~/usuba-hitcheck`.

## Analysis (on the box)
```sh
python3 analyze_results.py hitcheck-results.jsonl --md table.md --csv-prefix out/hc
```
Per rule: n, works, broken, unsure, and defect observable at three strengths: `direct` (the defect pattern itself seen at runtime: curl without a byte cap, a fixed /tmp file, sudo invoked, "Required property" load failure ...), `executed only` (the flagged script/command ran, the defective behaviour is not visible from outside, e.g. an unbounded python read), `static only` (file or code present, nothing at runtime), `none`.
Skip cases are a separate table; `direct` there would mean a skip condition hid a real defect.
Per pair: pre-fix broken?, pre-fix differs? (new warning/IPC/process/toggle signature compared with post-fix), post-fix works?, confirmed = (pre broken or differs) and post works; totals and by bug kind.

## Load verdict (same class-based rule as the private Dell-learnings notes; this section is the public statement of it)
broken = the shell died before s20, the plugin is not listed, a fatal QML message (not a type/module missing, syntax, failed to load, cannot create delegate, `Required property ... was not initialized`), a failing toggle on a panel/overlay/menu, or memory growth > 300 MB in 20 s.
unsure = harness failure (shell never answered IPC), a missing dependency binary, or a job timeout. works = everything else (other QML messages are warnings).

## Limits
- No screenshots or input: layout-only and click-path bugs (ui-layout pairs) can only show up through log lines or IPC output; expect many pairs of that kind to show "no difference". The rest of the pairs favour load/runtime-visible kinds.
- Network is off, so network defects are seen through the logged call (shim), not through traffic. Python/QML network code is only "executed", never "direct".
- The shell talks to a private runtime dir, so Hyprland/dbus/audio plugins show their "no connection" warnings; these are warnings, not failures. Re-run single jobs with `SESSION_ACCESS=1` if needed (shared runtime dir, read-only hyprctl).
