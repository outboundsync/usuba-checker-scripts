#!/usr/bin/env python3
"""S1 hardware-observable labels: Checker FAIL findings judged against hardware truth (box side; reads the earlier Dell sweep, nothing runs on the Dell here
except the optional one-line `type -P` check of the binaries a finding names).

Unit = (plugin, finding category). Truth comes from the Dell record of that plugin (24 s smoke, Omarchy 4.0.4), NOT from the sweep's `label` field, which for most
Checker failures is the Checker's own verdict (circular). Categories are split by what hardware can show:
  LOAD  load / instantiate / script-error classes     real_hw = shell died, not listed, toggle IPC failed or a fatal QML message;  warn_hw = non-fatal QML errors seen;
                                                       no_symptom_hw = clean record  -> FALSE-ALARM CANDIDATE (the smoke run may simply not reach the code path)
  BIN   names a binary the plugin needs               present_hw = installed on the Dell (type -P) or defined by the plugin itself -> FALSE ALARM;  absent_hw = absent and not defined -> real CANDIDATE (token may be prose)
  other (fake-data, destructive-cmd, heuristic USB-* style/semantic rules, invisible/zero-size widgets: need a screenshot judgement) -> not hardware-observable, excluded here
Everything is PROVISIONAL and eval-only. Plugins in r4/r5 training rows, the sealed holdout or the Dell key are dropped (repo and manifest id).

usage: python3 build_s1_hw.py --models ../models-checkout --out DIR [--bins-result DIR/bins_on_dell.json]
"""
import argparse
import collections
import glob
import gzip
import json
import os
import re
import sys

SWEEP = "/workspace/usuba-model-checker/dell/sweep"
LOAD = {"rt-load-failed", "rt-not-instantiated", "rt-qml-syntax", "rt-unresolved-type/import", "bad-import", "rt-shell-broken", "rt-bad-property", "rt-js-error",
        "rt-undefined-arg", "rt-plugin-warn", "rt-other", "singleton-unknown", "exec-undefined-arg"}
BIN = {"rt-missing-binary", "exec-unknown-binary", "usuba-USB-B01"}
FATAL = re.compile(r"is not a type|is not installed|module \S+ (is )?not (found|installed)|Failed to load|failed to load|SyntaxError|Expected token|Unexpected token|Type \S+ unavailable|Cannot open: \S+\.qml|Cannot create delegate|Required property .* was not initialized", re.I)
BINRX = re.compile(r"`([A-Za-z0-9_.+-]+)`")


def finding_text(r, cat):
    ck = r["checker"]
    msgs = [s for s in ck.get("static_fails") or [] if isinstance(s, str)] + [s for s in ck.get("runtime_errors") or [] if isinstance(s, str)]
    return msgs


def bins_of(msgs):
    out = set()
    for m in msgs:
        if "does not exist on the Dell" in m or "not installed on the Dell" in m or "not an Omarchy/system binary" in m:
            out |= set(BINRX.findall(m)[:1])
    return sorted(out)


def tree_text(d, cap=600_000):
    out, n = [], 0
    for r, ds, fs in os.walk(d or "/nonexistent"):
        ds[:] = [x for x in ds if x not in (".git", "node_modules")]
        for f in fs:
            if f.endswith((".sh", ".bash", ".qml", ".js", ".py")) or "." not in f:
                try:
                    t = open(os.path.join(r, f), encoding="utf-8", errors="replace").read(200_000)
                except OSError:
                    continue
                out.append(t)
                n += len(t)
                if n > cap:
                    return "\n".join(out)
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--bins-result")
    a = ap.parse_args()
    sys.path.insert(0, os.path.join(a.models, "train"))
    import holdout_guard as hg
    train_repos = set()
    for pat in ("/workspace/usuba-runs/v3-data-r5/*.jsonl*", "/workspace/usuba-runs/v3-data-r4/*.jsonl*"):
        for f in glob.glob(pat):
            for line in (gzip.open if f.endswith(".gz") else open)(f, "rt"):
                train_repos |= hg.row_repos(json.loads(line))
    guard = hg.Guard()
    present = json.load(open(a.bins_result)) if a.bins_result and os.path.exists(a.bins_result) else None
    os.makedirs(a.out, exist_ok=True)
    rows = [json.loads(line) for line in open(f"{SWEEP}/results.jsonl")]
    corpus_dir = {json.loads(line)["key"]: json.loads(line).get("local_dir") for line in open(f"{SWEEP}/corpus.jsonl")}
    stats = collections.Counter()
    items, binsneeded = [], set()
    for r in rows:
        ck = r.get("checker")
        if not ck or ck["pass_"] or r["label"] not in ("works", "broken", "unsure"):
            continue
        stats["Checker-FAIL plugins"] += 1
        key = r["key"].lower()
        if key in train_repos:
            stats["dropped: in r4/r5 train/val"] += 1
            continue
        if key in guard.repos or (r["plugin_id"] or "").lower() in guard.mids | guard.dell_ids:
            stats["dropped: sealed holdout / Dell key"] += 1
            continue
        d = r.get("dell")
        if not d or d.get("harness_invalid"):
            stats["dropped: no valid Dell record"] += 1
            continue
        hw_broken = bool(d.get("died") or d.get("listed") is False or d.get("toggle_ok") is False or any(FATAL.search(e) for e in d.get("qml_errors") or []))
        for cat in ck.get("categories") or []:
            msgs = finding_text(r, cat)
            it = dict(id=f"s1hw:{r['plugin_id']}:{cat}", kind="S1", plugin=r["key"], plugin_id=r["plugin_id"], commit=r["commit"], category=cat, checker_messages=[m[:300] for m in msgs[:3]],
                      dell=dict(run=d.get("run"), listed=d.get("listed"), toggle_ok=d.get("toggle_ok"), died=d.get("died"), qml_errors=(d.get("qml_errors") or [])[:3], missing_bins=d.get("missing_bins")),
                      provisional=True, eval_only=True)
            if cat in LOAD:
                it["group"] = "LOAD"
                it["hw_label"] = "real_hw" if hw_broken else ("warn_hw" if d.get("qml_errors") else "no_symptom_hw")
            elif cat in BIN:
                it["group"] = "BIN"
                bl = bins_of(msgs)
                it["binaries"] = bl
                binsneeded |= set(bl)
                tree = tree_text(corpus_dir.get(r["key"]))
                if not bl:
                    it["hw_label"] = "unresolved"
                elif present is None:
                    it["hw_label"] = "pending_bin_check"
                else:
                    miss = [b for b in bl if not present.get(b)]
                    defined = [b for b in miss if re.search(r"(^|\n)\s*(function\s+" + re.escape(b) + r"\b|" + re.escape(b) + r"\s*\(\s*\)\s*\{?)", tree)]
                    absent = [b for b in miss if b not in defined]
                    it["binaries_defined_in_plugin"] = defined
                    # present on the Dell, or defined by the plugin itself = the Checker named something that is not a missing dependency (false alarm);
                    # absent and not defined = real candidate (the token may still be prose or a variable, hence a candidate not a label)
                    it["hw_label"] = "absent_hw" if absent else "present_hw"
            else:
                stats["not hardware-observable finding categories"] += 1
                continue
            items.append(it)
    c = collections.Counter((i["group"], i["hw_label"]) for i in items)
    stats.update({f"S1hw {g}/{lab}": n for (g, lab), n in sorted(c.items())})
    stats["S1hw items"] = len(items)
    with open(f"{a.out}/s1_hw_items.jsonl", "w") as f:
        f.writelines(json.dumps(i) + "\n" for i in items)
    with open(f"{a.out}/bins_to_check.txt", "w") as f:
        f.writelines(b + "\n" for b in sorted(binsneeded))
    with open(f"{a.out}/s1_exclude_from_training.txt", "w") as f:
        f.writelines(k + "\n" for k in sorted({i["plugin"].lower() for i in items}))
    json.dump(dict(stats), open(f"{a.out}/s1_hw_stats.json", "w"), indent=1)
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()
