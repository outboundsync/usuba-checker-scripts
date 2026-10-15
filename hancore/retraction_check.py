#!/usr/bin/env python3
"""Date check: find HANCORE review findings that the reviewer later withdrew, in particular resource-allocation / unbounded-input blockers
written before 2026-10-03 (the 2026-10-03 disposition: resource-only concerns are not marketplace blockers; see docs/V3_FIXES.md).
Inputs : dell/sweep/hancore_reviews.jsonl (marketplace issue comments, dated); training rows (jsonl.gz, source == hancore_concrete; provenance.findings[].comment_url)
Model  : qwen/qwen3.5-397b-a17b via OpenRouter (open weights), temperature 0, reasoning off, data_collection deny. Every raw answer is cached in <out>/retraction_raw.jsonl
         (a re-run reuses the cache: no new spend, same result).
Steps  : (1) scan: every marketplace comment with an explicit withdraw/retract/rescind verb -> model extracts what is withdrawn and whether it is a resource-allocation item.
         (2) pairs: for each row finding, the later withdrawal comments of the same issue thread -> model decides withdrawn|maintained|unclear for THAT finding.
Outputs: withdrawals_scan.json, retraction_list.json, retraction_summary.json, retraction_cost.json (all under --out)
usage  : OPENROUTER_API_KEY=... python3 hancore/retraction_check.py --rows /workspace/usuba-runs/v3-data-r2/train.jsonl.gz /workspace/usuba-runs/v3-data-r2/val.jsonl.gz --out /workspace/usuba-runs/v3-fixes"""
import sys, os, json, gzip, re, time, argparse, collections, urllib.request, concurrent.futures as cf
H = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(H)
MODEL = "qwen/qwen3.5-397b-a17b"; CUTOFF = "2026-10-03"
RESOURCE_KINDS = {"unbounded-input-resource", "process-lifecycle-timeouts"}
W = re.compile(r"\b(withdr[ae]w\w*|retract\w*|rescind\w*|no longer (?:a |an )?blocker)\b", re.I)
SYS1 = ("You read one code-review comment from a marketplace reviewer. List every earlier objection/blocker the reviewer WITHDRAWS or no longer holds in this comment "
        "(not objections that are only fixed by the author, and not objections that remain). Answer JSON only: "
        '{"withdrawn": [{"topic": "<=15 words, generic, no names", "resource_allocation": true|false}], "withdraws_something": true|false}. '
        "resource_allocation = true when the withdrawn item is about unbounded reads, missing byte/size/memory caps, allocation, response/output size, or missing deadlines/timeouts.")
SYS2 = ("Decide whether the LATER comment withdraws the specific EARLIER finding. Answer JSON only: "
        '{"verdict": "withdrawn" | "maintained" | "unclear", "scope": "whole" | "part" | "none", "why": "<=25 words"}. '
        "withdrawn = the later comment says the reviewer no longer holds this finding as a blocker (even if for a stated reason such as local-only input). "
        "maintained = the later comment keeps it or only withdraws a different objection. unclear = cannot tell from the text.")
def call(system, user, key, cache, ck):
    if ck in cache: return cache[ck]
    body = dict(model=MODEL, messages=[{"role": "system", "content": system}, {"role": "user", "content": user}], max_tokens=400, temperature=0,
                reasoning={"enabled": False}, provider={"data_collection": "deny"}, response_format={"type": "json_object"}, usage={"include": True})
    err = None
    for att in range(4):
        try:
            req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=json.dumps(body).encode(), headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=180) as r: d = json.load(r)
            c = re.sub(r"<think>.*?</think>", "", d["choices"][0]["message"]["content"] or "", flags=re.S); m = re.search(r"\{.*\}", c, re.S)
            return dict(ans=json.loads(m.group(0)) if m else None, usage=d.get("usage", {}))
        except Exception as e: err = type(e).__name__; time.sleep(3 * (att + 1))
    return dict(ans=None, usage={}, error=err)
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--rows", nargs="+", required=True); ap.add_argument("--out", default="/workspace/usuba-runs/v3-fixes")
    ap.add_argument("--reviews", default=ROOT + "/dell/sweep/hancore_reviews.jsonl"); ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True); key = os.environ["OPENROUTER_API_KEY"]
    rawf = a.out + "/retraction_raw.jsonl"; cache = {}
    if os.path.exists(rawf):
        for l in open(rawf): d = json.loads(l); cache[d["ck"]] = d["out"]
    rv = [json.loads(l) for l in open(a.reviews)]; rv = [x for x in rv if x["thread_repo"] == "omacom/omarchy-plugin-marketplace"]; byurl = {x["url"]: x for x in rv}
    thread = collections.defaultdict(list)
    for x in rv: thread[x["thread"]].append(x)
    wds = [x for x in rv if W.search(x["text"])]
    def run(items, system):
        outs = {}
        with cf.ThreadPoolExecutor(a.workers) as ex:
            futs = {ex.submit(call, system, u, key, cache, ck): ck for ck, u in items}
            for f in cf.as_completed(futs): outs[futs[f]] = f.result()
        with open(rawf, "a") as fo:
            for ck, o in outs.items():
                if not o.get("error") and ck not in cache: cache[ck] = o; fo.write(json.dumps(dict(ck=ck, out=o)) + "\n")
        return outs
    sc = run([("scan:" + x["url"], x["text"][:3500]) for x in wds], SYS1)
    scan = []
    for x in wds:
        o = sc.get("scan:" + x["url"], {}).get("ans") or {}; wl = [w for w in o.get("withdrawn", []) if isinstance(w, dict)]
        scan.append(dict(url=x["url"], thread=x["thread"], date=x["date"], withdraws=bool(o.get("withdraws_something")), withdrawn=wl, resource=any(w.get("resource_allocation") for w in wl)))
    json.dump(scan, open(a.out + "/withdrawals_scan.json", "w"), indent=1)
    rows = []
    for f in a.rows: rows += [json.loads(l) for l in gzip.open(f)]
    rows = [r for r in rows if r["source"] == "hancore_concrete"]
    pairs = []; entries = []
    for r in rows:
        prov = r["provenance"] if isinstance(r["provenance"], dict) else json.loads(r["provenance"]); ftext = {}
        try: tgt = json.loads(r["messages"][-1]["content"]); ftext = {(f.get("file"), f.get("line")): f.get("finding") for f in tgt["findings"]}
        except Exception: pass
        for f in prov["findings"]:
            x = byurl.get(f["comment_url"])
            if not x: continue
            later = [w for w in thread[x["thread"]] if w["date"] > x["date"] and W.search(w["text"])]
            e = dict(row=r["id"], split=r["split"], bug_kind=f["bug_kind"], file=f["file"], line=f["line"], comment_url=f["comment_url"], comment_date=x["date"], before_cutoff=x["date"][:10] < CUTOFF,
                     resource_kind=f["bug_kind"] in RESOURCE_KINDS, finding_text=ftext.get((f["file"], f["line"])), candidates=[w["url"] for w in later], decisions=[])
            entries.append(e)
            for w in later:
                ck = "pair:" + f["comment_url"] + ">" + w["url"] + ":" + str(f["line"])
                u = f"EARLIER FINDING (kind {f['bug_kind']}, {f['file']}:{f['line']}): {(e['finding_text'] or x['text'])[:700]}\n\nEARLIER COMMENT EXCERPT:\n{x['text'][:1500]}\n\nLATER COMMENT:\n{w['text'][:3500]}"
                pairs.append((ck, u)); e["decisions"].append(dict(withdrawal=w["url"], withdrawal_date=w["date"], ck=ck))
    po = run(pairs, SYS2)
    for e in entries:
        for d in e["decisions"]:
            o = po.get(d["ck"], {}).get("ans") or {}; d.update(verdict=o.get("verdict", "error"), scope=o.get("scope"), why=o.get("why")); d.pop("ck")
        e["retracted"] = any(d["verdict"] == "withdrawn" and d["scope"] == "whole" for d in e["decisions"])
        e["retracted_partial"] = (not e["retracted"]) and any(d["verdict"] == "withdrawn" for d in e["decisions"])
    json.dump(entries, open(a.out + "/retraction_list.json", "w"), indent=1)
    ret = [e for e in entries if e["retracted"]]; part = [e for e in entries if e["retracted_partial"]]
    sm = dict(model=MODEL, cutoff=CUTOFF, hancore_findings=len(entries), rows=len(rows), withdrawal_comments_scanned=len(wds), scan_withdraws=sum(s["withdraws"] for s in scan), scan_resource=sum(s["resource"] for s in scan),
              scan_resource_dated_before_cutoff=sum(s["resource"] and s["date"][:10] < CUTOFF for s in scan), findings_with_later_withdrawal_candidate=sum(bool(e["candidates"]) for e in entries),
              retracted_whole=len(ret), retracted_whole_resource_kind=sum(e["resource_kind"] for e in ret), retracted_whole_before_cutoff=sum(e["before_cutoff"] for e in ret),
              retracted_partial=len(part), rows_with_retracted_finding=len({e["row"] for e in ret}), by_kind=dict(collections.Counter(e["bug_kind"] for e in ret)))
    json.dump(sm, open(a.out + "/retraction_summary.json", "w"), indent=1)
    tok = collections.Counter()
    for o in list(sc.values()) + list(po.values()):
        u = o.get("usage") or {}; tok["prompt"] += u.get("prompt_tokens", 0); tok["completion"] += u.get("completion_tokens", 0); tok["cost_usd"] += u.get("cost", 0) or 0
    json.dump(dict(calls_this_run=len(sc) + len(po), **{k: (round(v, 4) if k == "cost_usd" else v) for k, v in tok.items()}), open(a.out + "/retraction_cost.json", "w"), indent=1)
    print(json.dumps(sm, indent=1)); print(open(a.out + "/retraction_cost.json").read())
if __name__ == "__main__": main()
