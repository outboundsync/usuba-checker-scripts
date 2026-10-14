#!/usr/bin/env python3
"""Print the Dell-key leaderboard (markdown) from <name>.reason.json files. python3 eval/dellkey/table.py NAME[=Label] ..."""
import json, os, sys
RES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hancore_holdout", "results")
rows = []
for a in sys.argv[1:]:
    n, _, lab = a.partition("="); s = json.load(open(os.path.join(RES, n + ".reason.json")))["summary"]
    b = json.load(open(os.path.join(RES, n + ".json"))) if os.path.exists(os.path.join(RES, n + ".json")) else {}
    rows.append((lab or n, s, b.get("cost_usd")))
rows.sort(key=lambda r: (-r[1].get("right_reason_judge", r[1]["right_reason_det"]), r[1]["false_alarm"]))
print("| # | system | verdict acc | false alarms | broken caught | right-reason catches (judge) | of flagged | right-reason (regex) | invented SHA / name rows | parse | median s | $ |")
print("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
for i, (lab, s, c) in enumerate(rows, 1):
    caught = round(s["broken_caught"] * 33)
    print(f"| {i} | {lab} | {s['verdict_accuracy']:.3f} | {s['false_alarm']:.3f} | {s['broken_caught']:.3f} ({caught}/33) | {s.get('right_reason_judge','-')}/33 | {s.get('right_reason_judge_of_flagged', 0):.2f} | {s['right_reason_det']}/33 | {s['invented_sha_rows']} / {s['invented_name_rows']} | {s['parse_rate']:.3f} | {s['secs_median']} | {c if c is not None else '-'} |")
