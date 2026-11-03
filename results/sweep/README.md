# Omarchy plugin sweep: every plugin we could find, loaded on real hardware (Oct 2026)

`omarchy-plugin-sweep.csv` has one row per repo: 5,140 Omarchy plugin repos found through the plugin marketplace, GitHub search, GitHub code search and the AUR.

## How it was tested
- Each repo, at the exact `commit` listed, went through the Usuba Checker (static and runtime checks, see this repo).
- 4,922 were then loaded one at a time on a real laptop running Omarchy 4.0 alpha. For each one we installed it, restarted the shell, toggled it over IPC, and recorded whether the shell listed it or died, QML errors, missing binaries, leaked processes, CPU, RAM and files written.

## Verdicts
| verdict | rows | meaning |
|---|---:|---|
| works | 3,361 | Loaded and ran on the hardware with no hard errors, and the checker found no blocking issue. |
| broken | 1,197 | A hard failure. Either the hardware showed one (shell died, plugin not listed, toggle error, QML errors) or the checker did (unknown QML type, bad import, missing shipped file, placeholder or fake data, destructive command, and so on). See `reasons`. |
| unsure | 435 | Not a bug verdict. 423 loaded, but they call a program that stock Omarchy doesn't ship and the plugin doesn't bundle (for example `bw`, `sqlite3`, `scrcpy`, `cava`), so the feature couldn't be confirmed without installing it. 12 couldn't be fetched (the repo is deleted or private). |
| not-plugin | 144 | A theme, tool or other repo, not an Omarchy plugin. |
| dup | 3 | A duplicate of another row. |

## Columns
- `repo`, `url`, `commit`, `plugin_id`, `kinds`, `found_via`
- `verdict`, and `reasons`: every signal that fired, joined with ` | `. A `dell:` prefix means it was seen on the hardware.
- `checker_categories`: rule ids. `usuba-USB-*` rules are documented in this repo. For example, B01 is a missing binary, Q01 an unknown QML type, F01 a missing file, A0x API misuse, J0x manifest or JSON issues, and H07 a placeholder key.
- `dell_tested`, `dell_loaded`, `dell_died`, `dell_qml_errors`, `dell_missing_bins`, `dell_leaked_procs`, `dell_cpu_late_pct`, `dell_rss_mb`: the raw hardware signals.

## Caveats
- This is an automated sweep, not a hand review. Expect some false positives, especially broken rows flagged only by the checker, and plugins that need a key, hardware or a network before they draw anything.
- Results are for the commit listed. Many plugins have been fixed since.
- Plugins in our evaluation and holdout sets (539 repos) are left out on purpose, so they stay usable for scoring models.

License: these results are MIT, copyright OutboundSync. Each plugin keeps its own license.
