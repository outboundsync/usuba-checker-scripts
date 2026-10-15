#!/usr/bin/env python3
"""Generate REPORT.md, bugs.tsv, commits_all.jsonl, NOTICE, SHA256SUMS from data/*.jsonl and rows*.jsonl. Lessons text is in scripts/lessons.md (written from the data)."""
import json, collections, re, subprocess, statistics, hashlib, os
ROOT = '/workspace/ref/jankeesvw'
g = lambda repo, *a: subprocess.run(['git', '-C', f'{ROOT}/{repo}'] + list(a), capture_output=True, text=True, errors='replace').stdout
C = [json.loads(l) for l in open('data/commits.jsonl')]; CL = {(j['repo'], j['commit']): j['cls'] for j in map(json.loads, open('data/classes.jsonl'))}
B = [json.loads(l) for l in open('data/bugs_final.jsonl')]; BYK = {(b['repo'], b['commit']): b for b in B}
S = json.load(open('data/summary.json')); M = json.load(open('data/jv_rules_metrics.json')); RS = json.load(open('data/rows_stats.json'))
rows = {fn: [json.loads(l) for l in open(fn)] for fn in ('rows.jsonl', 'rows_tierB.jsonl', 'rows_extra.jsonl')}
REAL = [b for b in B if b['real_defect']]; J = [b for b in REAL if b['by_jankees']]
V2, V3 = 'v2', 'v3fixes_d00fcc0'; LAY = 'prompt+enabled'; ALL = 'all-rules'
# ---- commits_all.jsonl
with open('commits_all.jsonl', 'w') as f:
    for c in C:
        k = (c['repo'], c['commit']); b = BYK.get(k)
        f.write(json.dumps(dict(repo=c['repo'], commit=c['commit'], date=c['author_date'], author=c['author'], by_jankees=c['by_jankees'], subject=c['subject'], cls=CL[k],
                                bug=(dict(id=b['id'], real_defect=b['real_defect'], file=b['file'], line=b['line'], kind=b['kind'], category=b['category'], origin=b['origin']) if b else None),
                                files=[dict(path=x['path'], add=x['add'], dele=x['dele']) for x in c['files'] if not x['binary']], binary_files_skipped=sum(x['binary'] for x in c['files']))) + '\n')
with open('bugs.tsv', 'w') as f:
    f.write('id\trepo\tcommit\tdate\tauthor_is_jankees\tsubject\tfile\tline\tkind\tcategory\tfix_pattern\torigin\ttier\tverify\tlines_changed\tfiles_changed\tchecker_v2\tchecker_v3fixes\tdescription\n')
    for b in sorted(REAL, key=lambda x: (x['repo'], x['date'])):
        f.write('\t'.join(str(x).replace('\t', ' ').replace('\n', ' ') for x in [b['id'], b['repo'], b['commit'][:10], b['date'][:10], b['by_jankees'], b['subject'], b['file'], b['line'], b['kind'], b['category'], b['fix_pattern'], b['origin'], b['tier'], b['verify'], b['lines_changed'], len(b['files_changed']), b['checker'][V2][ALL]['outcome'], b['checker'][V3][ALL]['outcome'], b['description']]) + '\n')
# ---- numbers
cls_all = collections.Counter(CL.values()); cls_j = collections.Counter(CL[(c['repo'], c['commit'])] for c in C if c['by_jankees'])
by_auth = collections.Counter(c['by_jankees'] for c in C)
lines = [], 
L = []
w = L.append
w('# jankeesvw plugin history: the bugs he fixed and how he shipped fixes\n')
w('Generated 2026-10-15 (MT). Scope: 19 of his 21 repos (full history, all refs); `omarchy-clippy` (HANCORE holdout) and `omarchy-time-machine` (existing holdout) are excluded entirely and were never read. No GPU, no Dell commands, no pushes, no deletions. The Dell key labels and `eval/hancore_holdout` were not read. LLM: `qwen/qwen3.5-397b-a17b` via OpenRouter only (two passes, reasoning off, temperature 0; total spend printed in section 2).\n')
w(open('scripts/lessons.md').read())
w('\n## 2. Counts\n')
w(f"- Repos: 19 (full history; `omarchy-meeting-recorder` was a shallow clone and was unshallowed to 58 commits). Commits: **{len(C)}** (all refs), of which {by_auth[True]} authored by Jankees van Woezik, {by_auth[False]} by 56 other authors (PRs; Cursor Agent: 2), {cls_all['merge']} merge commits.")
w(f"- Classification of all {len(C)} commits: " + ', '.join(f'{k} {v}' for k, v in cls_all.most_common()) + '.')
w(f"- By his own commits only: " + ', '.join(f'{k} {v}' for k, v in cls_j.most_common()) + '.')
n_ver = len(B)
w(f"- First pass flagged {cls_all['bug_fix'] + cls_all['compat']} commits as bug fix/compat; **{n_ver}** have a mechanically verified pre-fix line (`removed` = the line is deleted/changed by the diff: {sum(b['verify']=='removed' for b in B)}; `adjacent` = pure-insertion fix, the line is within 3 lines of the insertion: {sum(b['verify']=='adjacent' for b in B)}; 3 dropped: quote mismatch/file missing). A second skeptical pass kept **{len(REAL)}** as real defects ({len(J)} his, {len(REAL)-len(J)} contributors'); tier A (functional/security/breakage) {sum(b['tier']=='A' for b in REAL)}, tier B (cosmetic/UX polish) {sum(b['tier']=='B' for b in REAL)}.")
w(f"- Origin of the {len(REAL)} real defects: " + ', '.join(f'{k} {v}' for k, v in collections.Counter(b['origin'] for b in REAL).most_common()) + '. `fix_of_fix` = the removed lines were last changed by an earlier commit classified bug fix (git blame). `regression_in_recent_feature` = introduced by the previous feature commit, not by a fix. `version_change` is limited to the two dated shell-compat events (10-09 `Commons.Color`, 10-13 new Omarchy shell): ' + f"{sum(b['version_event'] is not None for b in REAL)} commits, {sum(1 for b in REAL if b['version_event'] and '10-09' in b['version_event'])} on 10-09 and {sum(1 for b in REAL if b['version_event'] and '10-13' in b['version_event'])} on 10-13.")
w(f"- Fix shape (his {len(J)}): median {statistics.median(b['lines_changed'] for b in J)} changed lines, {statistics.median(len(b['files_changed']) for b in J)} files; {sum(any('manifest.json'==f['path'] for f in b['files_changed']) for b in J)} also bump the manifest version, {sum(any('README' in f['path'] for f in b['files_changed']) for b in J)} also edit the README, {sum(any(('test' in f['path']) for f in b['files_changed']) for b in J)} touch tests; {sum(len(next(c for c in C if c['commit']==b['commit'])['body'])>80 for b in J)} carry a body explaining cause and trigger.")
w(f"- Candidate rows (prompt_v3, MIT, source=jankeesvw-history): `rows.jsonl` {RS['main']['rows']} rows ({RS['main']['broken']} broken + {RS['main']['approve']} approve, max {RS['main']['max_tokens']} tokens, all <= 32000); `rows_tierB.jsonl` {RS['tierB']['rows']} (cosmetic/UX tier B); `rows_extra.jsonl` {RS['extra']['rows']} (version-compat commits beyond 3 per event). Dropped: {RS['drops']}. Approve rows are scarce on purpose: {RS['approve_dropped'].get('later_defect_still_present', 0)} post-fix trees still contained a defect that he fixed in a later commit, so they are not labelled approve. {RS['main']['over_v3_builder_caps']} main rows put the cited line beyond the v3 builder's 16000-char CITED_CAP (the whole cited file is shown here, which still fits 32k tokens).")
cost = sum(j.get('cost', 0) or 0 for f in ('data/classified.jsonl', 'data/review.jsonl') for j in map(json.loads, open(f)))
w(f'- LLM spend (qwen/qwen3.5-397b-a17b, OpenRouter, two passes, incl. retries logged): ${cost:.2f} of the $5 budget.')
# per kind table
w('\n## 3. Per-kind table (real defects)\n')
w('| kind | all | his | tier A | v3 rows (broken) | origin: orig / edge / fix-of-fix / regress / version | Checker HIT (v3-fixes d00fcc0, any layer) | FILE-only | MISS |')
w('|---|---|---|---|---|---|---|---|---|')
for k in ['load', 'qml', 'runtime', 'in-use', 'config', 'packaging', 'security']:
    s = [b for b in REAL if b['kind'] == k]
    if not s: continue
    o = collections.Counter(b['origin'] for b in s); oc = lambda a: sum(1 for b in s if b['checker'][V3][ALL]['outcome'] == a)
    nrow = sum(1 for r in rows['rows.jsonl'] if r['label'] == 'broken' and r['provenance']['bug_kind'] == k)
    w(f"| {k} | {len(s)} | {sum(b['by_jankees'] for b in s)} | {sum(b['tier']=='A' for b in s)} | {nrow} | {o['original_bug']} / {o['missed_edge_case']} / {o['fix_of_fix']} / {o['regression_in_recent_feature']} / {o['version_change']} | {oc('HIT')} | {oc('FILE')+oc('COINCIDENT')} | {oc('MISS')} |")
w('\nBy finer category (his + contributors):\n')
w('| category | n | fix patterns (top) |'); w('|---|---|---|')
cc = collections.defaultdict(list)
for b in REAL: cc[b['category']].append(b)
for k, v in sorted(cc.items(), key=lambda x: -len(x[1])):
    w(f"| {k} | {len(v)} | " + ', '.join(f'{a} {n}' for a, n in collections.Counter(b['fix_pattern'] for b in v).most_common(3)) + ' |')
# checker table
w('\n## 4. Checker hit/miss on the pre-fix trees\n')
w('Versions run on `git archive` snapshots of the pre-fix and post-fix tree of every real defect (both `rules` layers: what the prompt report shows plus enabled USB-H/HC rules, and "all rules" incl. experimental/off): **v2** = branch `checker-rules-v2` @57018c8, **v3-fixes** = branch `v3-fixes` @d00fcc0 (HEAD at run time; @763fe65 gave the same results as v2 on all 348 runs). Outcome per bug: **HIT** = a finding in the defect file within 5 lines of the defect whose rule category equals the bug category, or that disappears in the post-fix tree; **COINCIDENT** = a finding near the line for an unrelated reason (not credited); **FILE** = findings elsewhere in the file only; **MISS** = nothing in the file.\n')
w('| scope | version | rule layer | n | HIT | COINCIDENT | FILE | MISS |'); w('|---|---|---|---|---|---|---|---|')
for scope, sel in (('his', J), ('all real', REAL)):
    for ver in (V2, V3):
        for lay in (LAY, ALL):
            c = collections.Counter(b['checker'][ver][lay]['outcome'] for b in sel)
            w(f"| {scope} | {'v2' if ver==V2 else 'v3-fixes d00fcc0'} | {lay} | {len(sel)} | {c['HIT']} | {c['COINCIDENT']} | {c['FILE']} | {c['MISS']} |")
hits = [b for b in J if b['checker'][V3][ALL]['outcome'] == 'HIT' or b['checker'][V2][ALL]['outcome'] == 'HIT']
w(f"\nHits (his): " + '; '.join(f"`{b['repo']}@{b['commit'][:7]}` {b['file']}:{b['line']} ({', '.join(b['checker'][V3][ALL]['rules'])})" for b in hits) + '.')
w('\nNew candidate rules (`scripts/jv_rules.py`, regex only, advisory; recall measured on the same history they were derived from, so it is optimistic; false-fire measured on every HEAD of his repos and on a 250-plugin sample of other authors from /workspace/sweep_repos):\n')
w('| rule | what | recall@defect (bugs) | fires on HEAD of his repos | other plugins firing (of 250) |'); w('|---|---|---|---|---|')
for r, v in M.items(): w(f"| {r} | {v['summary']} | {v['pre_hits_at_defect_n']} | {v['head_fires']} | {v['external_plugins_firing']} |")
u = {i for r, v in M.items() if r not in ('USB-JV07', 'USB-JV08') for i in v['pre_hits_at_defect']}; u2 = {i for r, v in M.items() for i in v['pre_hits_at_defect']}
w(f"\nUnion recall of the 7 non-version rules: {len(u)} distinct bugs; with the two version-dependent rules: {len(u2)} of {len(REAL)} real defects. The existing Checker credits {len([b for b in REAL if b['checker'][V3][ALL]['outcome']=='HIT'])}. Most of what he fixed (logic, state, layout, lifecycle, edge cases: ~{round(100*sum(b['category'].split(':')[0] in ('runtime','in-use','qml') for b in REAL)/len(REAL))}%) is not statically detectable by regex; those are what the model has to learn from rows, not rules.")
w('\n### Per-bug table (his real defects; v2 / v3-fixes outcome, all-rules layer)\n')
w('| commit | date | file:line | category | origin | v2 | v3 | rule |'); w('|---|---|---|---|---|---|---|---|')
for b in sorted(J, key=lambda x: (x['repo'], x['date'])):
    w(f"| {b['repo'].replace('omarchy-','')}@{b['commit'][:7]} | {b['date'][:10]} | {b['file']}:{b['line']} | {b['category']} | {b['origin']} | {b['checker'][V2][ALL]['outcome']} | {b['checker'][V3][ALL]['outcome']} | {', '.join(b['checker'][V3][ALL]['rules'][:3])} |")
# samples
w('\n## 5. Ten sample pairs (broken = parent tree, approve/fixed = commit tree)\n')
pick = ['ed5835a', '8d979b5', 'f388a1b', 'b4dceeb', '99cf3b5', '1522a6e', '3a0607c', '730ac5b', 'b00a6ca', 'ab7b76a']
for n, sha in enumerate(pick, 1):
    b = next(x for x in REAL if x['commit'].startswith(sha)); df = g(b['repo'], 'diff', '-U1', '--no-renames', b['parent'], b['commit'], '--', b['file'])
    hunks = re.split(r'(?m)^(?=@@ )', df)[1:]; best = next((h for h in hunks if re.search(r'^@@ -(\d+)', h) and int(re.search(r'^@@ -(\d+)', h).group(1)) - 2 <= b['line'] <= int(re.search(r'^@@ -(\d+)', h).group(1)) + 40), hunks[0] if hunks else '')
    pair = [r for r in rows['rows.jsonl'] + rows['rows_extra.jsonl'] if r['id'].startswith(b['id']) and r['label'] == 'works']
    w(f"### {n}. `{b['repo']}` {b['commit'][:10]} ({b['date'][:10]}) {b['subject']}\n")
    w(f"- broken: `{b['file']}:{b['line']}` `{b['line_text'].strip()[:140]}`  | kind {b['kind']} / {b['category']} / fix {b['fix_pattern']} / origin {b['origin']} | Checker v3-fixes: {b['checker'][V3][ALL]['outcome']}")
    w(f"- description (the row's finding): {b['description']}")
    w(f"- symptom: {b['symptom']} Root cause: {b['root_cause']}")
    w(f"- row ids: `{b['id']}:broken`" + (f" + `{b['id']}:approve`" if pair else ' (no approve row: a later defect was still in the post-fix tree)'))
    w('```diff\n' + '\n'.join(best.splitlines()[:26]) + '\n```\n')
w('\n## 6. Files\n')
w('`rows.jsonl`, `rows_tierB.jsonl`, `rows_extra.jsonl` (prompt_v3 row schema); `bugs.tsv`, `data/bugs_final.jsonl` (every real defect with checker outcomes), `commits_all.jsonl` (every commit with class); `data/` (raw LLM passes, Checker runs, rule metrics); `scripts/` (replicable pipeline); `NOTICE`; `SHA256SUMS`. Replication: `docs/jankeesvw-history.md` on branch `jankeesvw-history` of the usuba repo.')
open('REPORT.md', 'w').write('\n'.join(L) + '\n')
# NOTICE
nt = ['NOTICE for rows*.jsonl (source=jankeesvw-history)', '', 'Text sources only (QML, JS, shell, Python, Rust, JSON, TOML, systemd units); no binary, audio or image assets are included (sound/screenshot/preview files are excluded by extension and by UTF-8 decode).', '',
      'All rows reproduce code from the repositories below, published under the MIT License. Each repository carries:', '', '    MIT License', '', '    Copyright (c) 2026 Jankees van Woezik', '',
      'Only commits authored by Jankees van Woezik are used as defect/fix pairs; the trees may also contain merged contributions that the repository license (MIT) covers. Permission notice (MIT): the above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND (see each repository LICENSE for the full text).', '', 'Repositories used (https://github.com/jankeesvw/<name>):']
used = sorted({r['provenance']['repo'] for v in rows.values() for r in v})
for u in used: nt.append(f'- {u}')
nt += ['', 'Excluded entirely: jankeesvw/omarchy-clippy (HANCORE holdout), jankeesvw/omarchy-time-machine (existing holdout).', 'Secrets, e-mail addresses and /home paths in code are redacted by the same scrub used for the v3 rows.']
open('NOTICE', 'w').write('\n'.join(nt) + '\n')
