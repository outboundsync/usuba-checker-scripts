#!/usr/bin/env python3
"""Build candidate training rows (prompt_v3 schema, same record fields as v3-fixes rows) from data/bugs_final.jsonl. No LLM, no network.
Prompt/Checker code: snapshot of branch v3-fixes d00fcc0 at /tmp/jh_snap/v3fixes-head (train/prompt_v3.py, train/checker_report.py). Tokenizer: Qwen3.5-9B tokenizer.json (32000-token ceiling, train max_len 32768).
broken row = parent (pre-fix) tree, finding = exact file:line + plain-words description; approve row = commit (post-fix) tree.
Selection: authored by Jankees van Woezik, real_defect, verified line, text source file; tier A -> data rows, tier B -> rows_tierB.jsonl; version-change compat commits capped at 3 per event (rest -> rows_extra.jsonl).
Approve row is dropped when a later verified defect of the same repo is still present in the post-fix file (the plugin was not clean then)."""
import json, os, re, subprocess, sys, collections, hashlib
SN = '/tmp/jh_snap/v3fixes-head'
sys.path[:0] = [SN + '/train', SN + '/functest']
import prompt_v3 as P, checker_report as CR, functest
from tokenizers import Tokenizer
TOK = Tokenizer.from_file(os.path.expanduser('~/.cache/huggingface/hub/models--Qwen--Qwen3.5-9B/snapshots/c202236235762e1c871ad0ccb60c8ee5ba337b9a/tokenizer.json'))
ntok = lambda s: len(TOK.encode(s).ids)
ROOT = '/workspace/ref/jankeesvw'; T = '/tmp/jh_trees'; MAX_TOK = 32000; V3_CITED_CAP = 16000
BADEXT = re.compile(r'\.(png|jpe?g|gif|webp|svg|ico|wav|mp3|ogg|flac|ttf|otf|woff2?|gz|zip|pdf|mp4|webm|lock)$', re.I)
sys.path.insert(0, SN + '/train'); from build_reviewer_scrub import scrub
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from archive_util import git_archive
HYG = re.compile(r"(?i)https?://|\b[0-9a-f]{7,40}\b|\bcommit\b|\bfix(ed|es)?\b|\breview\b|\bshould\b|\bconsider\b|\bearlier\b|\bPR\b|claude|anthropic|\bcomment\b|\bREADME\b")
def tree(repo, sha, tag):
    d = f'{T}/{repo}_{sha[:10]}_{tag}'
    if not os.path.exists(d + '/.ok'):
        git_archive(f'{ROOT}/{repo}', sha, d)
    return d
def read_files(d):
    fs = functest.read_dir(d)
    return {p: c for p, c in fs.items() if not BADEXT.search(p) and p not in CR.HARNESS_FILES and p != '.ok'}
def blob(files, cited_file, cited_line, budget_chars=95000):
    """manifest first, cited file next (whole file when it fits; else cut 60 lines after the cited line), then qml/js/sh/py/rs, README, rest. Line numbers stay those of the original file."""
    order = lambda p: (0 if p == 'manifest.json' or p.endswith('/manifest.json') else 1 if p == cited_file else 2 if p.endswith(('.qml', '.js', '.sh', '.py', '.lua', '.bash', '.rs')) or '/' not in p and '.' not in p or p.startswith('bin/') else 3 if p.lower().startswith('readme') else 4, p)
    out, n = [], 0; cut = {}
    for p in sorted(files, key=order):
        c = files[p]
        if p == cited_file and len(c) > 70000:
            ls = c.split('\n'); c = '\n'.join(ls[:cited_line + 60]); cut[p] = True
        if n + len(c) > budget_chars and p != cited_file and not p.endswith('manifest.json'): out.append(f"### {p}\n(omitted: {len(files[p])} chars)"); continue
        out.append(f"### {p}\n```\n{c}\n```"); n += len(c)
    return '\n\n'.join(out), cut
def scrub_files(files): return {p: scrub(c) for p, c in files.items()}
def target(b):
    load = 'unsure' if b['kind'] == 'security' else 'broken'
    f = re.sub(r'\s+', ' ', b['description']).strip()
    if len(f) > 300:
        f = f[:300]; f = f[:max(f.rfind('. '), f.rfind('; '), f.rfind(', '))].rstrip(' ,;') or f
    return dict(verdict='changes_requested', load=load, findings=[dict(category=b['category'], severity='blocker', file=b['file'], line=b['line'], finding=f)])
def main():
    B = [json.loads(l) for l in open('data/bugs_final.jsonl')]
    allbugs = [b for b in B if b['real_defect']]
    def usable(b):
        if not b['by_jankees'] or not b['real_defect']: return 'not_jankees_or_not_real'
        if b['file'].lower().startswith('readme') or b['file'].endswith('.md') or BADEXT.search(b['file']) or re.search(r'(^|/)\.', b['file']): return 'not_a_code_file'
        if HYG.search(b['description']) or len(b['description']) < 40: return 'description_hygiene'
        return None
    drops = collections.Counter(); cands = []
    for b in B:
        w = usable(b)
        if w: drops[w] += 1; continue
        cands.append(b)
    # cap version-change events
    seen = collections.Counter(); keep = []; extra = []
    for b in sorted(cands, key=lambda x: x['date']):
        if b['origin'] == 'version_change' and b['version_event']:
            seen[b['version_event']] += 1
            if seen[b['version_event']] > 3: extra.append(b); continue
        keep.append(b)
    rows = {'main': [], 'tierB': [], 'extra': []}; approve_dropped = collections.Counter(); sizes = []
    for group, lst in (('main', [b for b in keep if b['tier'] == 'A']), ('tierB', [b for b in keep if b['tier'] != 'A']), ('extra', extra)):
        for b in lst:
            pre = scrub_files(read_files(tree(b['repo'], b['parent'], 'pre'))); post = scrub_files(read_files(tree(b['repo'], b['commit'], 'post')))
            if b['file'] not in pre: drops['file_not_in_tree'] += 1; continue
            lines = pre[b['file']].split('\n')
            if b['line'] > len(lines): drops['line_out_of_range'] += 1; continue
            off = len('\n'.join(lines[:b['line']]))
            code, cut = blob(pre, b['file'], b['line']); rep = CR.report(pre)
            msgs = P.messages(code, rep, target(b)); tk = ntok(json.dumps(msgs))
            if tk > MAX_TOK: drops['over_token_cap'] += 1; continue
            prov = dict(kind='jankeesvw-history-fix', repo=f"jankeesvw/{b['repo']}", commit=b['commit'], parent=b['parent'], date=b['date'], author=b['author'], subject=b['subject'],
                        file=b['file'], line=b['line'], pre_fix_line_text=b['line_text'], verify=b['verify'], reanchored=b['reanchored'] or bool(b['line_note']), origin=b['origin'], origin_note=b['origin_note'],
                        bug_kind=b['kind'], category=b['category'], fix_pattern=b['fix_pattern'], tier=b['tier'], symptom=b['symptom'], root_cause=b['root_cause'], version_event=b['version_event'],
                        license='MIT', copyright='Copyright (c) 2026 Jankees van Woezik', notice='NOTICE', models=['qwen/qwen3.5-397b-a17b'], prompt='prompt_v3@v3-fixes:d00fcc0',
                        fits_v3_builder_caps=off <= V3_CITED_CAP, cited_file_truncated=bool(cut), checker_rep_lines=len(rep or []))
            rid = b['id']
            bro = dict(id=rid + ':broken', split='train', source='jankeesvw-history', orig_source='jankeesvw-history', synthetic=False, label='broken' if msgs else 'broken', verdict='changes_requested',
                       target_kind='jankeesvw_history_fix', reject_reason=None, is_pair_parent=True, pair=rid + ':approve', tokens=tk, provenance=prov, weight=1.0, messages=msgs)
            rows[group].append(bro)
            # approve (post-fix) row
            later = [x for x in allbugs if x['repo'] == b['repo'] and x['date'] > b['date'] and x['commit'] != b['commit'] and x['file'] in post and x['line_text'].strip() and x['line_text'].strip() in [l.strip() for l in post[x['file']].split('\n')] and len(x['line_text'].strip()) > 12]
            if later: approve_dropped['later_defect_still_present'] += 1; bro['is_pair_parent'] = False; bro['pair'] = None; bro['provenance']['approve_dropped'] = f"later defect still present: {later[0]['id']}"; continue
            if b['file'] not in post: approve_dropped['file_gone'] += 1; bro['is_pair_parent'] = False; bro['pair'] = None; continue
            repp = CR.report(post); am = P.messages(blob(post, b['file'], min(b['line'], len(post[b['file']].split('\n'))))[0], repp, dict(verdict='approve', load='works', findings=[]))
            atk = ntok(json.dumps(am))
            if atk > MAX_TOK: approve_dropped['over_token_cap'] += 1; bro['is_pair_parent'] = False; bro['pair'] = None; continue
            hard = [l for l in (repp or []) if re.search(r'heuristic/high|^\[USB-[A-Z]\d+\]', l)]
            ap = dict(id=rid + ':approve', split='train', source='jankeesvw-history', orig_source='jankeesvw-history', synthetic=False, label='works', verdict='approve', target_kind='jankeesvw_history_fixed', reject_reason=None,
                      is_pair_parent=False, pair=rid + ':broken', tokens=atk, provenance=dict(prov, kind='jankeesvw-history-fixed', note='post-fix tree; the cited defect is gone, other defects fixed in later commits are not present (checked by line text); approve is a pair label, not a full audit', checker_hard_lines_in_post=len(hard)), weight=0.5, messages=am)
            rows[group].append(ap)
    names = {'main': 'rows.jsonl', 'tierB': 'rows_tierB.jsonl', 'extra': 'rows_extra.jsonl'}
    for g, fn in names.items():
        with open(fn, 'w') as f:
            for r in rows[g]: f.write(json.dumps(r, ensure_ascii=False) + '\n')
    st = {g: dict(rows=len(r), broken=sum(x['label'] == 'broken' for x in r), approve=sum(x['label'] == 'works' for x in r), max_tokens=max([x['tokens'] for x in r] or [0]), over_v3_builder_caps=sum(not x['provenance']['fits_v3_builder_caps'] for x in r)) for g, r in rows.items()}
    st['drops'] = dict(drops); st['approve_dropped'] = dict(approve_dropped)
    json.dump(st, open('data/rows_stats.json', 'w'), indent=1); print(json.dumps(st))
main()
