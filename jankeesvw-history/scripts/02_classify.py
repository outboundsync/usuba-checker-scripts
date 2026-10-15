#!/usr/bin/env python3
"""Classify every non-merge commit with qwen/qwen3.5-397b-a17b (OpenRouter, open weights, no reasoning, temp 0).
Input data/commits.jsonl + git diffs (text files only, old-side line numbers shown so the model can cite an exact PRE-fix line).
Output data/classified.jsonl (resumable). Budget guard via BUDGET env (default $3)."""
import json, os, re, subprocess, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
KEY = os.environ['OPENROUTER_API_KEY']; MODEL = 'qwen/qwen3.5-397b-a17b'; BUDGET = float(os.environ.get('BUDGET', '3.0'))
ROOT = '/workspace/ref/jankeesvw'
EMPTY = '4b825dc642cb6eb9a060e54bf8d69288fbd3904'
CATS = ['load:component-not-created', 'load:undefined-property', 'load:undefined-identifier', 'load:unknown-type', 'load:missing-import', 'load:invalid-property', 'load:qml-type-error', 'load:missing-file',
        'qml:property-shadowing', 'qml:binding-or-layout', 'runtime:undefined-method', 'runtime:logic-error', 'runtime:state-or-race', 'runtime:parse-error', 'runtime:error-handling', 'runtime:resource-lifecycle',
        'in-use:missing-binary', 'in-use:invalid-command-arg', 'in-use:toggle-opens-nothing', 'in-use:panel-cannot-close', 'in-use:memory-growth', 'in-use:stale-or-wrong-display', 'in-use:data-loss',
        'config:wrong-path-or-env', 'config:placeholder-or-default', 'packaging:missing-file-or-manifest', 'packaging:install-deps',
        'unbounded-input-resource', 'process-lifecycle-timeouts', 'file-safety-symlink-perms', 'secrets-credentials', 'shell-lua-injection', 'rich-text-markup-injection', 'url-scheme-network', 'privileged-system', 'remote-code-pinning', 'other']
def g(d, *a):
    return subprocess.run(['git', '-C', d] + list(a), capture_output=True, text=True, errors='replace', timeout=120).stdout
def render_diff(c, cap=14000):
    d = f"{ROOT}/{c['repo']}"; par = c['parents'][0] if c['parents'] else EMPTY
    out = []; n = 0
    for f in c['files']:
        if f['binary']: out.append(f"##FILE {f['path']} (binary, skipped)"); continue
        if not c['parents']: out.append(f"##FILE {f['path']} (new file in root commit, +{f['add']} lines; not shown)"); continue
        df = g(d, 'diff', '-U3', '--no-renames', par, c['commit'], '--', f['path'])
        out.append(f"##FILE {f['path']}  (+{f['add']} -{f['dele']})")
        old = new = 0; lines = 0
        for l in df.splitlines():
            m = re.match(r'@@ -(\d+)(?:,\d+)? \+(\d+)', l)
            if m: old = int(m.group(1)); out.append(l.split('@@')[0] + '@@ ' + l.split('@@')[1] + '@@'); continue
            if l.startswith(('diff ', 'index ', '--- ', '+++ ', 'new file', 'deleted file')): continue
            if l.startswith('-'): out.append(f"-L{old}: {l[1:]}"); old += 1
            elif l.startswith('+'): out.append(f"+    : {l[1:]}")
            elif l.startswith('\\'): continue
            else: out.append(f" L{old}: {l[1:]}"); old += 1
            lines += 1
            if lines > 220: out.append('...(file diff truncated)'); break
        n = sum(len(x) + 1 for x in out)
        if n > cap: out.append('...(diff truncated)'); break
    return '\n'.join(out)[:cap + 400]
def prior(c, allc):
    xs = [x for x in allc if x['repo'] == c['repo'] and x['author_date'] < c['author_date'] and not x['is_merge']]
    xs.sort(key=lambda x: x['author_date']); return '\n'.join(f"{x['commit'][:7]} {x['author_date'][:10]} {x['subject'][:100]}" for x in xs[-8:]) or '(none, first commit)'
PROMPT = """You are an experienced Omarchy plugin developer reviewing one git commit of an Omarchy (Quickshell/QML + helper scripts) plugin repo. Omarchy shell compat events: 2026-10-09 (Qt 6.12 / Quickshell: `Color` singleton shadowed by Qt's own type -> `Commons.Color`) and 2026-10-13 ("new Omarchy shell" API/host change).
Repo: {repo}   commit {sha}   date {date}   author {author}
Subject: {subject}
Body: {body}
Previous commits in this repo (oldest first):
{prior}
Changed files (+/-): {files}
Diff (text files only; `-L<n>:` = removed line with its PRE-fix line number, ` L<n>:` = context line with its PRE-fix line number, `+    :` = added):
{diff}

Classify the commit. class is one of: bug_fix (the pre-fix code had a concrete defect: crash, wrong output, hang, leak, load failure, insecure handling, broken on a newer Omarchy/Quickshell/Qt/OS/tool version, missed edge case), compat (pure adaptation or migration with no concrete defect in pre-fix code visible), feature, refactor, docs, chore (version bump, assets, license, CI, screenshots, merge of upstream), release.
If the commit mixes a feature with a bug fix, class=bug_fix only when a distinct defect fix is in the diff, and cite the defect.
Answer JSON only:
{{"class": "...", "confidence": 0-1,
 "bug": null or {{
   "defect_file": "<path as in diff>", "defect_line": <PRE-fix line number (the L<n> number of a removed or context line that exhibits the defect; for a missing guard pick the context line the guard protects)>,
   "defect_line_text": "<exact text of that line after the 'L<n>: '>",
   "defect": "<=30 words, plain words, what is wrong in the pre-fix code at that line (no review framing, no mention of commits)",
   "symptom": "<=25 words: what the user/shell sees and when it triggers",
   "root_cause": "<=30 words",
   "category": one of {cats},
   "kind": one of ["load","qml","runtime","in-use","config","packaging","security"],
   "fix_pattern": one of ["guard-null-or-empty","timeout","size-cap","stdin-or-env-for-secret","state-dir-or-private-file","quote-or-escape","retry-or-backoff-or-debounce","reset-or-cleanup-lifecycle","wrong-condition-or-logic-fix","path-or-command-correction","api-rename-or-compat-shim","parse-more-robustly","bounds-clamp","ordering-or-race-fix","dependency-or-install-fix","ui-state-fix","revert","other"],
   "origin": one of ["version_change","missed_edge_case","followup_to_earlier_fix","revert","original_bug"],
   "origin_ref": "<short sha of the earlier commit it follows up/reverts or the compat event, or null>",
   "other_defects": "<other distinct bug fixes in the same commit, <=30 words, or null>"}}}}"""
def ask(c, allc):
    body = PROMPT.format(repo=c['repo'], sha=c['commit'][:10], date=c['author_date'][:10], author=c['author'], subject=c['subject'], body=c['body'][:600], prior=prior(c, allc),
                         files=', '.join(f"{f['path']}(+{f['add']}-{f['dele']}{',bin' if f['binary'] else ''})" for f in c['files'][:25]) or '(no file changes)', diff=render_diff(c), cats=CATS)
    req = dict(model=MODEL, messages=[dict(role='user', content=body)], max_tokens=700, temperature=0, reasoning=dict(enabled=False), usage=dict(include=True), response_format=dict(type='json_object'))
    err = None
    for t in range(3):
        try:
            rq = urllib.request.Request('https://openrouter.ai/api/v1/chat/completions', json.dumps(req).encode(), {'Authorization': 'Bearer ' + KEY, 'Content-Type': 'application/json'})
            j = json.load(urllib.request.urlopen(rq, timeout=90)); cost = j.get('usage', {}).get('cost') or 0
            txt = j['choices'][0]['message']['content'] or ''; v = json.loads(re.search(r'\{.*\}', txt, re.S).group(0))
            return dict(repo=c['repo'], commit=c['commit'], llm=v, cost=cost)
        except Exception as e: err = str(e)[:120]
    return dict(repo=c['repo'], commit=c['commit'], error=err)
if __name__ == '__main__':
    allc = [json.loads(l) for l in open('data/commits.jsonl')]
    out = 'data/classified.jsonl'; done = set()
    if os.path.exists(out): done = {(j['repo'], j['commit']) for j in map(json.loads, open(out)) if 'llm' in j}
    todo = [c for c in allc if not c['is_merge'] and (c['repo'], c['commit']) not in done]
    if len(sys.argv) > 1: todo = todo[:int(sys.argv[1])]
    spent = 0.0
    ex = ThreadPoolExecutor(12); f = open(out, 'a')
    futs = [ex.submit(ask, c, allc) for c in todo]
    try:
        for fu in as_completed(futs, timeout=int(os.environ.get('WALL', '900'))):   # unordered: one hung request cannot block the rest
            r = fu.result(); spent += r.get('cost', 0) or 0; f.write(json.dumps(r) + '\n'); f.flush()
    except Exception as e: print('wall-clock stop:', type(e).__name__)
    ex.shutdown(wait=False, cancel_futures=True)
    print('spent', round(spent, 3), 'n', len(todo))
