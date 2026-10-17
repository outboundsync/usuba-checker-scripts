# Dell hit-check: package, results and what they mean

Goal: confirm on the real Dell (Omarchy 4.0.4, real Quickshell) (A) that the Checker Scripts rules enabled on branch v3-fixes fire on plugins that load or misbehave in the way the rule claims, and (B) that 30 version-history bug pairs break before the fix and work after it.
Nothing here runs on the Dell by itself: the scripts build a package on the box; a person copies it to the Dell and runs one script. Package: `$PACKAGE_DIR/` (about 55 MB).

## Files (`tools/hitcheck/`)
- `build_package.py`: selection and package build (box). `finalize_package.sh`: copies scripts/README next to the tarballs and writes SHA256SUMS.
- `run_hitcheck.sh`: the one Dell-side script. `hc_signal.py`: run directory -> JSON line. `analyze_results.py`: JSONL -> tables. `README.md`: exact steps (shipped in the package).

## Replicate the build
```
python3 tools/hitcheck/build_package.py            # needs /workspace/usuba-runs/{checker-rules,v3-fixes,version-history}, /workspace/hancore_cache, /workspace/vh_repos, /workspace/sweep_repos
tools/hitcheck/finalize_package.sh
```
Seed `dell-hitcheck-1`; selection is deterministic.

## Selection
Batch A, rules = `enabled_v3_fixes` of `rules_v2_enabled.json` (USB-HC01, 02, 04, 05, 08, 09, 10, 15, 16, 17, 19, 20, 25) and the enabled lifecycle rules (USB-L02, L03, N01, N02).
1. For each rule take the 20 prepared samples of `checker-rules/dell_confirm_candidates.json` (v2 ids USB-H* = USB-HC* now) whose hit still fires under the current rule code (recomputed with `hancore_rules_v2.check` + `lifecycle_rules.check`), top up to 20 from the cached current hits of the design pool with a sha1 seed. USB-HC05 has 19 (its pool is small).
2. USB-L02: all 7 pool plugins with a hit. USB-L03, USB-N01 (2), USB-N02: no corpus hits, so synthetic plugins from `train/v3data/synthetic_lifecycle.py` (own work), plus 4 clean synthetic controls.
3. Skip cases (37 claims): prepared samples whose hit no longer fires, up to 5 more per skip rule (HC01, 02, 06, 18, 24) found by diffing the old rule code (branch checker-rules-v2, run from `git archive`) against the current code at line level, and the winners report cases (radio-atlas, omapods, github, omagotchi) computed the same way. Expectation: defect not observable.
4. Plugin root = the manifest.json directory containing the hit file (root manifest preferred). Excluded by ids/paths only (Dell labels never read): Dell key ids and near-duplicate trees, hancore_holdout repos/ids/trees, jankeesvw. Trees are copied without .git, symlinks, files > 1 MB, ELF/PE binaries.

Batch B: `version-history/data/verified_pairs.jsonl` (669 rows), MIT/ISC/BSD only (result: all MIT), file in .qml/.js/.sh/.py/.lua, seeded shuffle, quota per bug kind (api-compat 5, syntax 3, null guard 3, wrong path 3, error handling 3, process lifecycle 3, env/config 2, race 2, ui-layout 2, wrong condition 2, missing dependency 1, security 1; QML first), one pair per repo, plugin root found with `git ls-tree` at both commits (same root, same manifest id), trees via `git archive`.

## Run and analyse
See the package README. Result is `~/usuba-hitcheck/results/hitcheck-results.jsonl`; `analyze_results.py` prints the per-rule and per-pair tables.

## Finding while building: USB-HC17 raised on npm/pip/npx lines
`hancore_rules_v2.py` USB-HC17 built its match from `a and not b and (sh or py)` style expressions that evaluate to a boolean `True`, then called `.group(0)` on it: `AttributeError: 'bool' object has no attribute 'group'` for any file with a matching npm/pnpm/yarn/bun, pip/pipx/uv or npx/bunx/uvx line. The measurement scripts catch exceptions per plugin (`hits = []`), so every USB-HC hit of such a plugin silently went missing in `hits_hc_after.jsonl` (at least 31 of the 5,327 pool plugins; all the HC rules of those plugins). Fixed here in a separate commit (match object or None, same logic), 0 crashes on the pool afterwards. Numbers in `skip_effect.json` and the design-split metrics were not recomputed; the package therefore recomputes current hits itself instead of trusting the cached ones.

## Dry run on the box
16 plugins (synthetic rule cases, controls, one pair) ran in headless sway with the sandbox: `b01-meviusisback__keybinds-plugin` pre = broken (`Unexpected token` in KeybindsPanel.qml), post = works; the synthetic USB-L03 plugin = broken (`Required property shell was not initialized`); the clean control works. Quickshell derives its instance id from pid and time, so parallel jobs in separate pid namespaces collided on one runtime dir; each job now gets a private runtime dir (only the Wayland socket is bound in).

## Plugin trees are not redistributed
The package tarballs (`plugins-A.tar.gz`, `plugins-B.tar.gz`) are not in this repository: only 54 of the 344 trees carry a LICENSE file. Instead `tools/hitcheck/plugins_manifest.json` lists repo, plugin root, rule claims and (Batch B) exact pre and post commits, and `tools/hitcheck/fetch_plugins.py --out pkg` rebuilds the package layout from the public repos. Batch A commits were not recorded at sweep time, so a fresh fetch uses the current HEAD and line numbers may have moved. The raw per-job result JSONL is not published; `results/hitcheck/` holds the table and the two CSVs.

## Results (results/hitcheck/table.md, hc_A_claims.csv, hc_B_pairs.csv)
**Batch A, direct observation of the claimed defect, per enabled rule (n sampled plugins):** USB-HC01 20/20; USB-HC08 3/20; USB-HC10 2/20; USB-HC15 2/20; USB-HC04 1/20; USB-HC02, HC05, HC09, HC17, HC19, HC20, HC25: 0 observed. USB-HC16 is a static policy rule (static evidence only). USB-L02, HC19, HC20, HC25 had executed-only evidence (the code ran, no defect seen). USB-L03 and USB-N02 were observed once each, on synthetic sample plugins. Clean controls: 4/4 load and show no defect. Two third-party plugins in the rule samples failed to load for reasons unrelated to the sampled rule (a QML syntax error under HC16, a missing type under HC25).
**Skip cases:** the old USB-HC01 hit that the v3-fixes skip conditions suppress still showed the defect 6/6 times, so those skip conditions may hide real defects and should be revisited. The other skip cases (HC02, 05, 06, 08, 13, 15, 17, 18, 24) showed none.
**Batch B (30 version-history pairs, pre-fix = parent commit, post-fix = fix commit):** 30/30 pre and post trees differ and 29/30 post-fix trees work, but only 2 pre-fix trees were actually broken and only 1 pair shows broken-before, works-after (`b01-meviusisback__keybinds-plugin`, QML parse error). The other "confirmed" pairs are counted as confirmed when the behaviour differs (process set, IPC or warnings), which is weaker evidence. **Miss:** `b29-herman6888__newswire-omarchy` (wrong-condition-or-logic): pre and post both fail to load (`herman.newswire-zh` Widget.qml fatal), so the fix is not confirmed (29/30, not 30/30).

## Consequence for rule status
`functest/usuba/rule_hardware_status.json` (`HARDWARE_STATUS` in `hancore_rules_v2.py`) records the evidence class per rule. Only rules with a directly observed defect may be described as breaking a plugin on hardware: USB-HC01 (always), USB-HC04/08/10/15 (sometimes), USB-L03 and USB-N02 (synthetic only). Every other enabled rule is a static advisory (security, hygiene or robustness): USB-HC02, 05, 09, 16, 17, 19, 20, 25, L02, N01 must not be labelled as breaking on hardware. `tests/test_rule_hardware_status.py` enforces the labelling.
