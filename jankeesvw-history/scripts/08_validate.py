#!/usr/bin/env python3
"""Validate rows*.jsonl: prompt_v3 prefix identical, target schema, cited line really is the pre-fix line in the prompt text, tokens <= 32000, keys equal to v3-fixes rows, exclusions, banned words."""
import json, sys, re, os, collections
SN = '/tmp/jh_snap/v3fixes-head'; sys.path[:0] = [SN + '/train', SN + '/functest']
import prompt_v3 as P
from build_reviewer_scrub import scrub
from tokenizers import Tokenizer
TOK = Tokenizer.from_file(os.path.expanduser('~/.cache/huggingface/hub/models--Qwen--Qwen3.5-9B/snapshots/c202236235762e1c871ad0ccb60c8ee5ba337b9a/tokenizer.json'))
KEYS = set(json.loads(open('/workspace/usuba-runs/v3-fixes/synthetic_rows.jsonl').readline()).keys())
pref = P._prefix(); bad = collections.Counter(); n = 0; ids = set()
for fn in ('rows.jsonl', 'rows_tierB.jsonl', 'rows_extra.jsonl'):
    for l in open(fn):
        r = json.loads(l); n += 1
        if set(r) != KEYS: bad['keys'] += 1
        if r['id'] in ids: bad['dup_id'] += 1
        ids.add(r['id'])
        if r['messages'][:len(pref)] != pref: bad['prefix'] += 1
        if len(TOK.encode(json.dumps(r['messages'])).ids) > 32000: bad['over32k'] += 1
        if r['source'] != 'jankeesvw-history' or r['provenance']['license'] != 'MIT': bad['source_license'] += 1
        if re.search(r'omarchy-clippy|time-machine', json.dumps(r['provenance'])): bad['excluded_repo'] += 1
        if re.search(r'(?i)bitter|hand-checked', json.dumps(r)): bad['banned_word'] += 1
        t = json.loads(r['messages'][-1]['content']) if r['messages'][-1]['role'] == 'assistant' else None
        if t is None: bad['no_target'] += 1; continue
        if t['verdict'] not in ('approve', 'changes_requested') or t['load'] not in ('works', 'broken', 'unsure'): bad['target_schema'] += 1
        if r['label'] == 'broken':
            f = t['findings'][0]; u = r['messages'][-2]['content']
            if not (f['severity'] == 'blocker' and isinstance(f['line'], int) and len(f['finding']) <= 300 and f['file'] and set(f) == {'category', 'severity', 'file', 'line', 'finding'}): bad['finding_schema'] += 1
            m = re.search(r'### ' + re.escape(f['file']) + r'\n```\n(.*?)\n```(?:\n\n###|\Z)', u, re.S)
            if not m: bad['file_block_missing'] += 1; continue
            ls = m.group(1).split('\n')
            if f['line'] > len(ls) or ls[f['line'] - 1].strip() != scrub(r['provenance']['pre_fix_line_text']).strip(): bad['cited_line_mismatch'] += 1
        else:
            if t['findings'] != [] or t['verdict'] != 'approve': bad['approve_schema'] += 1
print('rows', n, 'problems', dict(bad))
sys.exit(1 if bad else 0)
