#!/usr/bin/env python3
"""Builds results_v3.json, dell_confirm_candidates.json, examples_v3.json and README_v3 section from metrics_v3_*.json. No Dell commands; samples are from the non-Dell pool (design split)."""
import sys, os, json, random, collections
H = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(H); sys.path[:0] = [H, os.path.join(ROOT, "functest/usuba")]
import measure_v3 as M
OUT = M.OUT
pool = json.load(open(OUT + "/pool.json")); F = json.load(open(OUT + "/findings.json")); hits = {}
for fn in ("hits.jsonl", "hits_model.jsonl"):
    for l in open(OUT + "/" + fn): d = json.loads(l); hits.setdefault(d["repo"], []).extend(d["hits"])
en = json.load(open(ROOT + "/functest/usuba/rules_v2_enabled.json")); enabled = en["enabled_v3"]
import hancore_rules_v2 as V
# ---- dell confirm candidates: ~20 hit samples per enabled rule, design split, seeded, mix of HANCORE file-matched and unmatched
def line_of(src, f, n):
    try: L = open(os.path.join(src, f), encoding="utf-8", errors="replace").read().split("\n"); return "\n".join(f"{i+1}: {L[i][:200]}" for i in range(max(0, n - 2), min(len(L), n + 1)))
    except Exception: return ""
cand = {}
for rule in enabled:
    cat = V.RULES[rule][0]; rnd = random.Random("dell-confirm:" + rule); pool_hits = []
    for repo, hs in hits.items():
        r = pool[repo]
        if r["split"] != "design": continue
        fl = [f for f in F.get(repo, []) if f["cat"] == cat and not f["clean"]]
        cited = {c for f in fl for c in f["files"]}
        for h in hs:
            if h["rule"] != rule: continue
            st = "hancore_file_match" if any(M.fmatch(h["file"], c) for c in cited) else ("hancore_category_other_file" if fl and cited else ("hancore_category_no_file" if fl else "no_hancore_finding"))
            pool_hits.append((repo, h, st, r))
    byplug = {}; [byplug.setdefault(x[0], x) for x in sorted(pool_hits, key=lambda x: (x[0], x[1]["file"], x[1]["line"]))]  # one hit per plugin
    items = list(byplug.values()); rnd.shuffle(items)
    A = [x for x in items if x[2] == "hancore_file_match"]; B = [x for x in items if x[2] != "hancore_file_match"]
    pick = A[:8] + B[:12]; pick += [x for x in items if x not in pick][:max(0, 20 - len(pick))]
    cand[rule] = dict(category=cat, summary=V.RULES[rule][1], n_design_plugins_fired=len(items), samples=[dict(repo=x[0], plugin_src_path=x[3]["src"], file=x[1]["file"], line=x[1]["line"], abs_path=os.path.join(x[3]["src"], x[1]["file"]), reason=x[1]["reason"], snippet=line_of(x[3]["src"], x[1]["file"], x[1]["line"]), hancore_status=x[2]) for x in pick[:20]])
json.dump(dict(note="For LATER Dell confirmation; nothing was run on the Dell. Plugins are from the non-Dell design pool (paths are on the box). hancore_status says how the hit relates to HANCORE's finding text (never Dell labels). One hit per plugin, seeded sample.", rules=cand), open(OUT + "/dell_confirm_candidates.json", "w"), indent=1)
print("dell candidates", {k: len(v["samples"]) for k, v in cand.items()})
# ---- results_v3.json
R = {sp: json.load(open(OUT + f"/metrics_v3_{sp}.json")) for sp in ("design", "test", "all")}
json.dump(R, open(OUT + "/results_v3.json", "w"), indent=1)
# ---- examples_v3 (design hits of new rules in plugins whose HANCORE findings name the file)
ex = {r: [s for s in cand[r]["samples"] if s["hancore_status"] == "hancore_file_match"][:3] for r in cand if int(r[-2:]) >= 19}
json.dump(ex, open(OUT + "/examples_v3.json", "w"), indent=1)
# ---- README v3 section
before = {"file-safety-symlink-perms": (0.058, 0.366), "privileged-system": (0.429, 0.376), "process-lifecycle-timeouts": (0.0, None), "remote-code-pinning": (0.055, 0.355), "rich-text-markup-injection": (0.0, None),
          "secrets-credentials": (0.027, 0.343), "shell-lua-injection": (0.0, None), "unbounded-input-resource": (0.227, 0.406), "url-scheme-network": (0.052, 0.316)}
f = lambda x: "-" if x is None else (f"{x:.3f}" if isinstance(x, float) else str(x))
L = []
L.append("\n\n# v3 update: file-level matching, finding-level recall, model-assisted rules USB-HC19..H25\n")
L.append("Everything above this line is the v2 write-up (plugin-level counting) and is kept unchanged for comparison. Files from v3: results_v3.json, metrics_v3_{design,test,all}.json, findings.json (finding table), cands_raw/ (raw model replies), cands.json + cands_design_metrics.json (all 111 model candidates, design metrics), cands_decisions.json (keep/drop reason per candidate), hits_model.jsonl (hits of H19-H25), examples_v3.json, dell_confirm_candidates.json.\n")
L.append("## Measurement fixes (hancore/findings_v3.py, hancore/measure_v3.py)\n- **Finding-level counting**: the unit is one HANCORE strong/likely category finding at the reviewed commit (a plugin with 3 findings in a category counts 3), not a plugin. Findings whose prose says 'no high/medium issue identified' but carry a category tag (215 of 10,187) are excluded as clean-review noise (v2 counted them as positives).\n- **File-level matching**: files (and file:line) named in the finding prose are parsed (extensions qml/sh/py/js/lua/json/md/conf/... plus extensionless `bin/x:12`); a hit matches if its file path equals/suffix-matches/has the same basename as a named file. 5,516 of ~9,970 findings name a file (parsed). Findings naming no file can only be judged at plugin level.\n- **recall_file** = recalled findings / findings with parsed files (recalled = a rule of the set hit one of the named files). **recall_plugin** = finding-weighted share with any hit of the set in the plugin (the loose v2-like number, now finding-counted). **recall_blend** = file-level for parsed, plugin-level for unparsed, over all findings.\n- **File-level lower-bound precision** (plugin-file, strict): fired reviewed plugin is TP only if a hit lands in a file HANCORE names for that category; FP if the plugin has no same-category finding or its findings name other files; plugins whose same-category findings name no file are INDETERMINATE and excluded from strict (counted FP in 'lower', TP in 'upper'). Still a lower bound: HANCORE does not name every vulnerable file.\n- **Bug kinds**: keyword taxonomy over finding prose (hancore/findings_v3.py KINDS; a finding can have several kinds; 'other' = none matched). It is a heuristic, not human labelling.\n")
def tab(split, setn):
    d = R[split]["sets"][setn]; rows = []
    for c, s in d.items():
        rows.append(f"| {c} | {', '.join(x[-3:] for x in s['rules']) or '-'} | {s['findings']} / {s['findings_parsed']} | {f(s['recall_file'])} | {f(s['recall_plugin'])} | {f(s['plugin_precision_nc'])} | {f(s['plugin_file_precision_strict'])} / {f(s['plugin_file_precision_lower'])} / {f(s['plugin_file_precision_upper'])} | {f(s['false_hit'])} |")
    return "\n".join(rows)
H_ = "| category | rules | findings / with file | recall (file-level) | recall (finding-weighted, plugin-hit) | plugin precision (clean-filtered) | plugin-file precision strict / lower / upper | false-hit |\n|---|---|---|---|---|---|---|---|"
L.append("## Before vs after, per category (split = all reviewed pool; enabled rules)\nv2 columns are the original README numbers (plugin-level, enabled rules, all splits).\n")
L.append("| category | v2 recall | v2 precision | v3-def, OLD enabled: recall file / plugin | OLD: precision plugin / file-strict | v3-def, NEW enabled (H01-H25): recall file / plugin | NEW: precision plugin / file-strict | NEW false-hit |\n|---|---|---|---|---|---|---|---|")
for c in before:
    o = R["all"]["sets"]["old_enabled"][c]; n = R["all"]["sets"]["new_enabled"][c]
    L.append(f"| {c} | {f(before[c][0])} | {f(before[c][1])} | {f(o['recall_file'])} / {f(o['recall_plugin'])} | {f(o['plugin_precision_nc'])} / {f(o['plugin_file_precision_strict'])} | {f(n['recall_file'])} / {f(n['recall_plugin'])} | {f(n['plugin_precision_nc'])} / {f(n['plugin_file_precision_strict'])} | {f(n['false_hit'])} |")
for sp in ("design", "test"):
    L.append(f"\n### {sp} split, NEW enabled set (H01-H25)\n" + H_ + "\n" + tab(sp, "new_enabled"))
L.append("\n### test split, OLD enabled set (H01-H18 enabled subset), for the same-definition delta\n" + H_ + "\n" + tab("test", "old_enabled"))
L.append("\n## Recall per bug kind (all split, NEW enabled set; kinds with >=15 findings; recall_file over findings that name a file)\n| category | kind | findings | with file | recall file | recall plugin |\n|---|---|---|---|---|---|")
for c, s in R["all"]["sets"]["new_enabled"].items():
    for k, v in s["kinds"].items():
        if v["n"] >= 15: L.append(f"| {c} | {k} | {v['n']} | {v['n_parsed']} | {f(v['recall_file'])} | {f(v['recall_plugin'])} |")
L.append("\n## Per rule (file-level), all enabled/experimental/dropped rules, test split | design split\n| rule | category | enabled(v3) | design: fired/P/lift/FH/Pfile-strict/Rfile | test: fired/P/lift/FH/Pfile-strict/Rfile |\n|---|---|---|---|---|")
for k in sorted(R["design"]["rules"]):
    a = R["design"]["rules"][k]; b = R["test"]["rules"][k]; cat = V.RULES[k][0]
    g = lambda v: f"{v['fired_reviewed']}/{f(v['plugin_precision'])}/{v['lift']}/{f(v['false_hit'])}/{f(v['plugin_file_precision_strict'])}/{f(v['recall_file'])}"
    L.append(f"| {k} {V.RULES[k][1][:50]} | {cat} | {'yes' if k in enabled else 'no'} | {g(a)} | {g(b)} |")
dec = json.load(open(OUT + "/cands_decisions.json")); raw = [json.load(open(p)) for p in __import__('glob').glob(OUT + "/cands_raw/*.json")]
cost = sum(r["usage"].get("cost", 0) for r in raw)
L.append(f"\n## Model-assisted rules (part 1)\n- Model: qwen/qwen3.5-397b-a17b (open weights) via OpenRouter only; {len(raw)} calls (2 per weak category, 30 DESIGN-split findings each: HANCORE prose + cited source lines, selected among findings the existing rules missed), reasoning effort low, provider data_collection=deny. Total cost ${cost:.2f} (budget $15). API key read from the environment, never printed or written.\n- Categories prompted: secrets, file-safety, url-network, remote-code-pinning, rich-text, shell-lua, process-lifecycle (note: only 2 rounds each were possible for most categories because few missed design findings with cited lines exist: {{secrets 112, file-safety 126, url 78, pinning 66, rich-text 74, shell-lua 46}} missed).\n- {len(dec)} candidate specs after parse/regex-safety/dedupe; {sum(d['passes_numeric_gate'] for d in dec.values())} passed the numeric design gate (lift>=1.5 and false-hit<=0.05); 7 kept after the additional guards (>=20 fired reviewed plugins, not redundant with an enabled rule, semantically sound, category fits): USB-HC19..H25. Every decision with reason is in cands_decisions.json. Specs are data-only (model_rules_v3.json; regexes are compile- and ReDoS-screened; no model code is executed).\n- Nothing for rich-text, process-lifecycle or file-safety survived (best lifts 1.25 / 1.38 / 1.43).\n\n### Survivors, design (decision) vs test (read once, after freezing)\n| rule | category | design fired/P/lift/FH | test fired/P/lift/FH | verdict |\n|---|---|---|---|---|")
verd = {"USB-HC19": "holds on test", "USB-HC20": "holds, borderline lift 1.50", "USB-HC21": "marginal on test (lift 1.48)", "USB-HC22": "FAILS test (lift 0.97)", "USB-HC23": "weak on test (lift 1.18)", "USB-HC24": "weak on test (lift 1.41, no file-level hits)", "USB-HC25": "holds on test"}
for k in sorted(r for r in enabled if int(r[-2:]) >= 19):
    a = R["design"]["rules"][k]; b = R["test"]["rules"][k]
    L.append(f"| {k} {V.RULES[k][1]} | {V.RULES[k][0]} | {a['fired_reviewed']}/{f(a['plugin_precision'])}/{a['lift']}/{f(a['false_hit'])} | {b['fired_reviewed']}/{f(b['plugin_precision'])}/{b['lift']}/{f(b['false_hit'])} | {verd[k]} |")
L.append("\nThe enabled list was NOT edited after seeing test (to keep the split honest); rules_v2_enabled.json `enabled_v3` still contains H22-H24. Recommendation: demote H22, H23, H24 (and consider H21) to experimental.\n\n## Caveats\n- Lower-bound precision stays a lower bound: HANCORE names a subset of vulnerable files, so file-level strict precision (0.1-0.3) understates true precision; but it is also the honest number for 'does the hit point at what a reviewer flagged'. The old plugin-level 0.31-0.43 was inflated by plugin-level matching (any finding in the category anywhere in the plugin) and by clean-review findings counted as positives.\n- Recall remains low for the weak categories: file-level recall of enabled rules is secrets 0.04, file-safety 0.02-0.04, url 0.05, pinning 0.07; the model rules lifted file-level recall to secrets 0.02->0.05, pinning 0.05->0.10, shell-lua 0.00->0.125 (all splits) but shell-lua precision stays ~0.15 plugin / 0.09 file-strict. Model-proposed regexes mostly re-found patterns already covered or produced broad, low-precision rules; ~20 rules/category is not enough to cover reviewer judgement (design/logic bugs, per-plugin context).\n- Multiple comparisons: 111 candidates were screened on design; 20 passed the gate, so some design lift is selection luck (test shows it: 4 of 7 survivors fail, are weak or marginal). Test split was read once for the 7 survivors (and once for the old rules' v3-definition numbers); test numbers for H01-H18 had been seen in v2.\n- Bug-kind labels are keyword heuristics; a finding naming several categories shares its file list across categories; findings without a file name (45%) are only judged at plugin level.\n- Not done: no Dell command was run and no Dell label was read; dell_confirm_candidates.json lists 20 design-split hit samples (8 HANCORE-file-matched + 12 other where available) per enabled rule (17 rules) for later confirmation. Pool/paths are box paths.\n- Model rules USB-HC21/22/23 overlap each other (all 'string concatenated into a shell argv'); H19 flags pip installs lacking --hash even if version-pinned; H20/H25 flag credential-bearing requests with default redirect handling (potential leak, not proof).\n")
s = open(OUT + "/README.md").read()
if "# v3 update" in s: s = s.split("\n\n# v3 update")[0]
open(OUT + "/README.md", "w").write(s + "\n".join(L))
print("README updated", len(L))
