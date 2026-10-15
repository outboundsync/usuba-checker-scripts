#!/usr/bin/env python3
"""Reason-graded scoring for the Dell answer key (86 decided rows after excluding the decided rows of 6 Claude-written plugins; was 90).

A flagged broken plugin counts as a right-reason catch only if one of the reviewer's findings names the real failure from
functest/dell_ground_truth.jsonl (file + cause; line within tolerance when the key has one).
Two graders:
  det   deterministic regex rubric (reason_rubric.json): file mention AND cause pattern AND (line within tolerance if both sides cite one)
  judge open-weights LLM judge (default openai/gpt-oss-120b, or qwen/qwen3.5-397b-a17b, a slower thinking model; judge_rubric.md) via OpenRouter, zero data retention (provider.zdr), key from $OPENROUTER_API_KEY (never printed)
The reported right-reason metric is the judge's when it ran, else det; both and their agreement are stored.
Also counts hallucinations: invented commit SHAs (hex runs of 7-40 chars not present in the prompt input) and plugin names
(reverse-domain plugin ids, or quoted plugin names, that are not this plugin's manifest id/name and not in the input).

usage: python3 eval/dellkey/reason_grade.py RESULT_NAME [...] [--judge] [--judge-model M]
Reads eval/hancore_holdout/results/<name>.raw.jsonl, writes <name>.reason.json and adds keys to <name>.json."""
import argparse, json, os, re, sys, time, urllib.request, collections
OPEN_JUDGES = ["openai/gpt-oss-120b", "qwen/qwen3.5-397b-a17b"]   # open-weights (Apache-2.0) judges, grading only
EXCLUDED_ID_PREFIXES = ("b3.opus55.",)   # Claude-written plugins are not used as eval items (86 decided rows remain of 90; the 6 plugins include 2 undecided rows)
H = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(H)); RES = os.path.join(ROOT, "eval", "hancore_holdout", "results")
sys.path[:0] = [os.path.join(ROOT, "functest")]
RUB = json.load(open(os.path.join(H, "reason_rubric.json"))); TOL = RUB["line_tolerance"]
JUDGE_SYS = open(os.path.join(H, "judge_rubric.md")).read()
KEY = {g["id"]: g for g in map(json.loads, open(os.path.join(ROOT, "functest", "dell_ground_truth.jsonl"))) if g["real_verdict"] in ("WORKS", "BROKEN") and not g["id"].startswith(EXCLUDED_ID_PREFIXES)}


def parse(txt):
    if (txt or "").startswith(("ERROR ", "SKIPPED")): return None   # transport/context errors are invalid output, even though they contain JSON
    txt = re.sub(r"<think>.*?</think>", "", txt or "", flags=re.S).strip()
    m = re.search(r"\{.*\}", txt, re.S)
    if not m: return None
    try: return json.loads(m.group(0))
    except Exception: return None
def findings(out):
    F = [f for f in (out or {}).get("findings") or [] if isinstance(f, dict)]
    B = [f for f in F if str(f.get("severity", "")).lower() == "blocker"]
    return B or F
def ftext(f): return " ".join(str(f.get(k) or "") for k in ("category", "file", "finding"))
def det_match(pid, F):
    r = RUB["rules"][pid]
    for i, f in enumerate(F):
        t = ftext(f)
        if r["files"] and not any(x.lower() in t.lower() for x in r["files"]): continue
        if not any(re.search(c, t, re.I) for c in r["cause"]): continue
        if r["line"]:
            nums = [int(n) for n in re.findall(r"(?::|line\s*|L)(\d{2,5})\b", t, re.I)]
            if nums and not any(abs(n - r["line"]) <= TOL for n in nums): continue
        return True, i
    return False, None

def input_text(pid):
    """Everything the model was shown about the plugin (files + checker report), for hallucination checks."""
    import functest; g = KEY[pid]
    d = next(x for x in (os.path.join(ROOT, g["path"]), os.path.join("/workspace/omarchy-specialist", g["path"])) if os.path.isdir(x))
    files = {p: c for p, c in functest.read_dir(d).items() if p not in ("SOURCE.txt", "checklist.md")}   # same as run_eval.strip_harness
    return "\n".join(list(files) + list(files.values())), files
HEX = re.compile(r"(?<![0-9a-zA-Z])[0-9a-f]{7,40}(?![0-9a-zA-Z])")
PID = re.compile(r"\b(?:[a-z][a-z0-9-]*\.){2,}[a-z0-9][a-z0-9-]*\b")
FILE_EXT = (".tmp", ".bak", ".log", ".lock", ".cache", ".yaml", ".yml", ".ini", ".html", ".xml", ".so", ".desktop", ".service", ".qml", ".js", ".json", ".sh", ".py", ".md", ".txt", ".conf", ".lua", ".toml", ".css", ".svg", ".png", ".mjs")
CODE_OBJ = {"root", "os", "self", "this", "parent", "shell", "json", "math", "qt", "quickshell", "sys", "subprocess", "window", "model", "modeldata", "console", "process", "proc", "settings", "config", "manifest", "plugin", "item", "data", "path", "str", "re"}
def hallucinations(pid, raw, out, cache={}):
    if pid not in cache: cache[pid] = input_text(pid)
    inp, files = cache[pid]
    try: man = json.loads(files.get("manifest.json", "{}"))
    except Exception: man = {}
    own = {str(man.get("id", "")).lower(), str(man.get("name", "")).lower(), pid.lower()}
    txt = json.dumps(out) if out is not None else (raw or "")
    shas = sorted({h for h in HEX.findall(txt) if re.search(r"\d", h) and (re.search(r"[a-f]", h) or len(h) >= 12) and h not in inp}
                  | {h for h in re.findall(r"commit\W{0,3}([0-9a-f]{6,40})\b", txt, re.I) if h not in inp})
    names = set()
    for m in PID.findall(txt):
        ml = m.lower()
        if ml.split(".")[0] in CODE_OBJ: continue   # code member access like root.settings.save, os.path.isdir
        if ml.endswith(FILE_EXT) or ml in own or m in inp or re.match(r"^(qs|quickshell|qt|org\.kde|io\.qt)\.", ml): continue
        if re.search(r"\.(com|org|net|io|dev|app|ai|co|gov|edu|me)$", ml) and not re.match(r"^(io|com|org|dev|me|net)\.", ml): continue   # hostnames
        names.add(m)
    for m in re.findall(r"(?:plugin|Plugin)(?: widget| service| overlay| panel| bar)?\s+`?([a-z0-9][\w-]*\.[\w.-]*[\w-])", txt):
        if not m.lower().endswith(FILE_EXT) and m.lower() not in own and m not in inp: names.add(m)
    for m in re.findall(r"(?:plugin|Plugin)\s+[\"'`]([^\"'`]{3,40})[\"'`]", txt):
        if m.lower() not in own and m not in inp: names.add(m)
    return shas, sorted(names)

def judge(a, pid, F):
    g = KEY[pid]
    user = json.dumps(dict(plugin=pid, ground_truth=g["reason"], summary=RUB["rules"][pid]["summary"],
                           reviewer_findings=[dict(index=i, category=f.get("category"), severity=f.get("severity"), file=f.get("file"), finding=str(f.get("finding"))[:1500]) for i, f in enumerate(F)]), ensure_ascii=False)
    body = dict(model=a.judge_model, temperature=0, max_tokens=4000, messages=[{"role": "system", "content": JUDGE_SYS}, {"role": "user", "content": user}],
                reasoning={"effort": "low"}, provider={"zdr": True, "data_collection": "deny"}, usage={"include": True})
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"]})
    for i in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r: j = json.load(r)
            spent = (j.get("usage") or {}).get("cost", 0) or 0; o = parse(j["choices"][0]["message"].get("content"))
            if not o or "match" not in o: raise ValueError("judge reply was not the JSON asked for")
            return bool(o.get("match")), o.get("why"), spent
        except Exception as e:
            if i == 3: return None, f"judge error {type(e).__name__}", 0
            time.sleep(4 * (i + 1))

def grade(a, name):
    sfx = getattr(a, "suffix", "")
    R = [json.loads(l) for l in open(os.path.join(RES, name + ".raw.jsonl"))]
    rows, cost = [], 0.0; jc = {}
    R = [r for r in R if not r["plugin"].startswith(EXCLUDED_ID_PREFIXES)]
    for r in R:
        pid = r["plugin"]; out = parse(r.get("raw")) if r.get("raw") is not None else None
        flagged = r.get("verdict") == "changes_requested"
        shas, names = hallucinations(pid, r.get("raw"), out)
        row = dict(plugin=pid, label=r["label"], flagged=flagged, valid=out is not None, secs=r.get("secs"), invented_shas=shas, invented_names=names)
        if r["label"] == "positive":
            F = findings(out); row["det"], row["det_idx"] = det_match(pid, F) if flagged else (False, None)
            if a.judge and flagged and F:
                row["judge"], row["judge_why"], c = judge(a, pid, F); cost += c
            elif a.judge: row["judge"], row["judge_why"] = False, "not flagged or no findings"
        rows.append(row)
    pos = [x for x in rows if x["label"] == "positive"]; neg = [x for x in rows if x["label"] == "negative"]
    caught = [x for x in pos if x["flagged"]]
    rr = lambda k: sum(bool(x.get(k)) for x in pos)
    s = sorted(x["secs"] for x in rows if x["secs"] is not None)
    res = dict(name=name, n=len(rows), n_broken=len(pos), verdict_accuracy=round((len(caught) + sum(not x["flagged"] for x in neg)) / len(rows), 3),
               broken_caught=round(len(caught) / len(pos), 3), false_alarm=round(sum(x["flagged"] for x in neg) / len(neg), 3),
               parse_rate=round(sum(x["valid"] for x in rows) / len(rows), 3), secs_median=s[len(s) // 2] if s else None,
               right_reason_det=rr("det"), right_reason_det_of_broken=round(rr("det") / len(pos), 3), right_reason_det_of_flagged=round(rr("det") / max(1, len(caught)), 3),
               invented_sha_rows=sum(bool(x["invented_shas"]) for x in rows), invented_sha_count=sum(len(x["invented_shas"]) for x in rows),
               invented_name_rows=sum(bool(x["invented_names"]) for x in rows), invented_name_count=sum(len(x["invented_names"]) for x in rows))
    if a.judge:
        both = [x for x in pos if x["flagged"] and x.get("judge") is not None]
        res.update(right_reason_judge=rr("judge"), right_reason_judge_of_broken=round(rr("judge") / len(pos), 3),
                   right_reason_judge_of_flagged=round(rr("judge") / max(1, len(caught)), 3),
                   det_judge_agreement=round(sum(bool(x["det"]) == bool(x["judge"]) for x in both) / max(1, len(both)), 3), judge_cost_usd=round(cost, 4), judge_model=a.judge_model)
    res["right_reason_of_flagged"] = res.get("right_reason_judge_of_flagged", res["right_reason_det_of_flagged"])
    json.dump(dict(summary=res, rows=rows), open(os.path.join(RES, name + sfx + ".reason.json"), "w"), indent=1)
    p = os.path.join(RES, name + ".json")
    if os.path.exists(p) and not sfx:
        base = json.load(open(p)); base["reason"] = res; json.dump(base, open(p, "w"), indent=1)
    return res

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("names", nargs="+"); ap.add_argument("--judge", action="store_true")
    ap.add_argument("--judge-model", default=OPEN_JUDGES[0], help="open-weights judge via OpenRouter; known good: " + ", ".join(OPEN_JUDGES))
    ap.add_argument("--allow-closed-judge", action="store_true", help="permit a non-open judge (never an Anthropic model: provider terms forbid using Claude outputs as eval labels)")
    ap.add_argument("--suffix", default="", help="tag appended to output file names so a second judge does not overwrite the first, e.g. --suffix .gptoss")
    a = ap.parse_args()
    if a.judge:
        if a.judge_model.lower().startswith("anthropic/") or "claude" in a.judge_model.lower(): sys.exit("refusing: Anthropic/Claude models may not be used as judges here; use an open-weights judge")
        if a.judge_model not in OPEN_JUDGES and not a.allow_closed_judge: sys.exit(f"judge {a.judge_model} is not on the open-weights list {OPEN_JUDGES}; pass --allow-closed-judge to override")
    for n in a.names: print(json.dumps(grade(a, n)))
