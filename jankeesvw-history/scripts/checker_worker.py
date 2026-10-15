#!/usr/bin/env python3
"""usage: checker_worker.py SNAPSHOT_ROOT TREE_DIR -> JSON list of Checker findings on stdout.
SNAPSHOT_ROOT holds functest/ and train/ of one Checker version (git archive of branch checker-rules-v2 or v3-fixes).
Layers: 'report' = what the prompt shows (checker_report.report_and_warn_rules: checks.check + experimental W rules + v3 lifecycle rules where present);
'hc' = USB-HC rules (hancore_rules_v2.check, enabled set and the full set; not in the prompt report)."""
import json, os, re, sys, importlib
root, tree = sys.argv[1], sys.argv[2]
sys.path.insert(0, root + '/train'); sys.path.insert(0, root + '/functest')
import functest
files = {p: c for p, c in functest.read_dir(tree).items()}
import checker_report as CR
out = []
def line_of(reason):
    m = re.search(r'\bline[s]? (\d+)', reason or ''); return int(m.group(1)) if m else None
try:
    from usuba import checks
    for f in checks.check(files):
        out.append(dict(layer='report', rule=f['rule'], file=f.get('file'), line=f.get('line') or line_of(f.get('reason')), sev=f.get('severity'), text=checks.fmt(f)[:300]))
except Exception as e: out.append(dict(layer='error', text='checks:' + repr(e)[:200]))
try:
    from usuba import hancore_rules as HR
    for f in HR.check(files, experimental=True):
        out.append(dict(layer='report' if f['rule'] in HR.EXPERIMENTAL else 'report-off', rule=f['rule'], file=f['file'], line=f.get('line'), sev=f.get('severity'), text=f['reason'][:300]))
except Exception as e: out.append(dict(layer='error', text='W:' + repr(e)[:200]))
try:
    from usuba import lifecycle_rules as LR
    for f in LR.check(files, enabled={"USB-N01", "USB-N02", "USB-L01", "USB-L02", "USB-L03"}):
        out.append(dict(layer='report', rule=f['rule'], file=f['file'], line=f.get('line'), sev=f.get('severity'), text=f['reason'][:300]))
except ImportError: pass
except Exception as e: out.append(dict(layer='error', text='LC:' + repr(e)[:200]))
try:
    from usuba import hancore_rules_v2 as H2
    en = H2.ENABLED
    for f in H2.check(files, enabled=set(H2.RULES)):
        out.append(dict(layer='hc' if f['rule'] in en else 'hc-off', cat=H2.RULES[f['rule']][0], rule=f['rule'], file=f['file'], line=f.get('line'), sev=f.get('severity'), text=f['reason'][:300]))
except Exception as e: out.append(dict(layer='error', text='HC:' + repr(e)[:200]))
print(json.dumps(out))
