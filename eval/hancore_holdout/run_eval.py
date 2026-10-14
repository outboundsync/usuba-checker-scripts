#!/usr/bin/env python3
"""Head-to-head on the frozen HANCORE holdout (329 plugins: 300 positive, 29 negative). Never used for training.

Backends (same Usuba skill prompt, train/prompt.py, for every model):
  --backend checker                         Usuba Checker scripts alone (USB-W rule -> category map), no model
  --backend openai --base-url URL --model M  any OpenAI-compatible endpoint:
        local 9B:  llama-server -m usuba-9b-Q4_K_M.gguf -c 16384 --port 8080  ->  --base-url http://127.0.0.1:8080/v1 --model usuba-9b
        frontier:  --base-url https://openrouter.ai/api/v1 --model <frontier id>   (key read from $OPENROUTER_API_KEY, never printed)
  Thinking is OFF by default for every backend (training used enable_thinking=False); pass --think to allow it.
  --backend dry                             build prompts and score an always-'changes_requested' baseline (pipeline smoke test)
Metrics: verdict accuracy, positive recall (changes_requested on a positive), false-alarm rate on negatives, per-category recall of HANCORE
finding categories (strong/likely findings at the reviewed commit), category precision, JSON-valid rate, $ cost (from usage tokens and
--price-in/--price-out per 1M tokens), seconds per plugin. Output: eval/hancore_holdout/results/<name>.json (+ raw .jsonl)."""
import argparse, json, os, re, sys, tarfile, time, collections, urllib.request
from concurrent.futures import ThreadPoolExecutor
H = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(H))
sys.path[:0] = [os.path.join(ROOT, "train"), os.path.join(ROOT, "functest")]
import prompt
from build_reviewer_scrub import scrub
CODE_CAP, FILE_CAP = 24000, 8000
W_MAP = {"USB-W01": "install-deps-packaging", "USB-W02": "secrets-credentials", "USB-W03": "remote-code-pinning", "USB-W04": "file-safety-symlink-perms",
         "USB-W05": "privileged-system", "USB-W06": "rich-text-markup-injection", "USB-W07": "shell-lua-injection", "USB-W08": "process-lifecycle-timeouts",
         "USB-W09": "url-scheme-network", "USB-W10": "unbounded-input-resource"}
SCORED = set(W_MAP.values()) | {"scope-policy-duplicate", "user-config-modification", "listing-metadata-docs"}

def files_of(arc):
    out = {}
    with tarfile.open(os.path.join(H, arc)) as t:
        for m in t.getmembers():
            if m.isfile() and m.size < 2_000_000:
                try: out[m.name.split("/", 1)[-1]] = t.extractfile(m).read().decode("utf-8")
                except Exception: pass
    return out
def code_blob(files):
    order = lambda p: (0 if p == "manifest.json" else 1 if p.endswith((".qml", ".js", ".sh", ".py", ".lua", ".bash")) else 2 if p.lower().startswith("readme") else 3, p)
    out, n = [], 0
    for p in sorted(files, key=order):
        c = files[p][:FILE_CAP]
        if n + len(c) > CODE_CAP: out.append(f"### {p}\n(omitted: {len(files[p])} chars)"); continue
        out.append(f"### {p}\n```\n{c}\n```"); n += len(c)
    return "\n\n".join(out)
def checker(files):
    from usuba import checks, hancore_rules as HR
    try: rep = [checks.fmt(f) for f in checks.check(files)]
    except Exception: rep = None
    w = HR.check(files, experimental=True)
    rep2 = [f"[{f['rule']} warn{' experimental' if f['rule'] in HR.EXPERIMENTAL else ''}] {f['file']}: {f['reason']}" for f in w if f["rule"] in HR.EXPERIMENTAL]
    return ((rep or []) + rep2 if rep is not None else None), {W_MAP[f["rule"]] for f in w if f["rule"] in W_MAP}

def parse(txt):
    txt = re.sub(r"<think>.*?</think>", "", txt or "", flags=re.S).strip()
    m = re.search(r"\{.*\}", txt, re.S)
    try: return json.loads(m.group(0)) if m else None
    except Exception: return None
def call_openai(a, msgs):
    body = dict(model=a.model, messages=msgs, temperature=0, max_tokens=a.max_tokens)
    if not a.think:   # parity with training (enable_thinking=False -> empty <think></think> block)
        if "openrouter.ai" in a.base_url: body["reasoning"] = {"enabled": False, "exclude": True}
        else: body["chat_template_kwargs"] = {"enable_thinking": False}   # llama-server needs --jinja for this
    if a.provider: body["provider"] = {"order": [a.provider], "allow_fallbacks": False}
    hdr = {"Content-Type": "application/json"}
    key = os.environ.get(a.key_env) if a.key_env else None
    if key: hdr["Authorization"] = "Bearer " + key
    req = urllib.request.Request(a.base_url.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(), headers=hdr)
    for i in range(4):
        try:
            with urllib.request.urlopen(req, timeout=600) as r: j = json.load(r)
            return j["choices"][0]["message"].get("content") or "", j.get("usage") or {}
        except Exception as e:
            if i == 3: return f"ERROR {type(e).__name__}", {}
            time.sleep(5 * (i + 1))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["checker", "openai", "dry"], required=True); ap.add_argument("--name", required=True)
    ap.add_argument("--base-url"); ap.add_argument("--model"); ap.add_argument("--key-env", default=None)
    ap.add_argument("--price-in", type=float, default=0.0); ap.add_argument("--price-out", type=float, default=0.0)
    ap.add_argument("--max-tokens", type=int, default=2048); ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--think", action="store_true", help="allow thinking (default off, matching training)")
    ap.add_argument("--provider", default=None, help="OpenRouter provider pin"); ap.add_argument("--limit", type=int, default=0); a = ap.parse_args()
    M = [json.loads(l) for l in open(os.path.join(H, "manifest.jsonl"))]
    if a.limit: M = M[:a.limit]
    def one(m):
        files = files_of(m["code_archive"]); rep, wcats = checker(files)
        gt = {c for f in m["findings"] if f.get("strength") in ("strong", "likely") for c in f["categories"]} & SCORED
        t0 = time.time(); usage = {}; raw = None
        if a.backend == "checker":
            out = dict(verdict="changes_requested" if wcats else "approve", findings=[{"category": c} for c in sorted(wcats)])
        elif a.backend == "dry":
            msgs = prompt.messages(scrub(code_blob(files)), [scrub(r) for r in rep] if rep is not None else None)
            out = dict(verdict="changes_requested", findings=[], _prompt_chars=sum(len(x["content"]) for x in msgs))
        else:
            msgs = prompt.messages(scrub(code_blob(files)), [scrub(r) for r in rep] if rep is not None else None)
            raw, usage = call_openai(a, msgs); out = parse(raw)
        secs = time.time() - t0
        pred = {(f.get("category") or "") for f in (out or {}).get("findings", []) if isinstance(f, dict)}
        pred |= {c for f in (out or {}).get("findings", []) if isinstance(f, dict) for c in (f.get("also") or [])}
        return dict(plugin=m["plugin"], label=m["label"], gt=sorted(gt), pred=sorted(pred), verdict=(out or {}).get("verdict"), valid=out is not None,
                    secs=round(secs, 2), usage=usage, raw=raw if raw is None else raw[:4000])
    with ThreadPoolExecutor(a.workers) as ex: R = list(ex.map(one, M))
    pos = [r for r in R if r["label"] == "positive"]; neg = [r for r in R if r["label"] == "negative"]
    flag = lambda r: r["verdict"] == "changes_requested"
    cat = {}
    for c in sorted(SCORED):
        tp = sum(1 for r in R if c in r["gt"] and c in r["pred"]); fn = sum(1 for r in R if c in r["gt"] and c not in r["pred"]); fp = sum(1 for r in R if c not in r["gt"] and c in r["pred"])
        cat[c] = dict(gt=tp + fn, recall=round(tp / (tp + fn), 3) if tp + fn else None, precision=round(tp / (tp + fp), 3) if tp + fp else None)
    tin = sum(r["usage"].get("prompt_tokens", 0) for r in R); tout = sum(r["usage"].get("completion_tokens", 0) for r in R)
    tp_all = sum(len(set(r["gt"]) & set(r["pred"])) for r in R); gt_all = sum(len(r["gt"]) for r in R); pr_all = sum(len(set(r["pred"]) & SCORED) for r in R)
    s = sorted(r["secs"] for r in R)
    res = dict(name=a.name, backend=a.backend, model=a.model, n=len(R), positives=len(pos), negatives=len(neg),
               verdict_accuracy=round((sum(flag(r) for r in pos) + sum(not flag(r) for r in neg)) / len(R), 3),
               positive_recall=round(sum(flag(r) for r in pos) / max(1, len(pos)), 3), negative_false_alarm=round(sum(flag(r) for r in neg) / max(1, len(neg)), 3),
               category_recall_micro=round(tp_all / max(1, gt_all), 3), category_precision_micro=round(tp_all / max(1, pr_all), 3),
               json_valid=round(sum(r["valid"] for r in R) / len(R), 3), tokens_in=tin, tokens_out=tout,
               cost_usd=round(tin / 1e6 * a.price_in + tout / 1e6 * a.price_out, 4), secs_median=s[len(s)//2], secs_total=round(sum(s), 1), per_category=cat)
    od = os.path.join(H, "results"); os.makedirs(od, exist_ok=True)
    json.dump(res, open(os.path.join(od, a.name + ".json"), "w"), indent=1)
    with open(os.path.join(od, a.name + ".raw.jsonl"), "w") as f:
        for r in R: f.write(json.dumps(r) + "\n")
    print(json.dumps({k: v for k, v in res.items() if k != "per_category"}, indent=1))
if __name__ == "__main__": main()
