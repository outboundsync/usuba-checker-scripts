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
    nb = s.get("n_broken", 33); caught = round(s["broken_caught"] * nb)
    print(f"| {i} | {lab} | {s['verdict_accuracy']:.3f} | {s['false_alarm']:.3f} | {s['broken_caught']:.3f} ({caught}/{nb}) | {s.get('right_reason_judge','-')}/{nb} | {s.get('right_reason_judge_of_flagged', 0):.2f} | {s['right_reason_det']}/{nb} | {s['invented_sha_rows']} / {s['invented_name_rows']} | {s['parse_rate']:.3f} | {s['secs_median']} | {c if c is not None else '-'} |")

# Dell CPU baseline rows (open models only), appended to the final table. Different, tiny subset (8 plugins): not comparable to the full-key broken rows above.
if "--no-dell" not in os.environ.get("TABLE_OPTS", ""):
    bp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dell_baseline.json"); d = json.load(open(bp))
    print(f"\nDell baseline (local CPU, {d['n']} broken plugins only, a small sample; one plugin = 12.5 points). Open models only.")
    print("| system | right reason | loose | wrong | no flag | invented SHA |")
    print("|---|---:|---:|---:|---:|---:|")
    for r in d["rows"]:
        print(f"| {r['system']} | {r['right_reason']}/{d['n']} | {r['loose']} | {r['wrong']} | {r['no_flag']} | {r['invented_sha']}/{d['n']} |")
