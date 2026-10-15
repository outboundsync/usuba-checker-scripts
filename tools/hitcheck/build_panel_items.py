#!/usr/bin/env python3
"""Build judge-panel input (models/tools/judge_panel.py) from the S1 hardware items and the S2 candidates. The panel is BLIND to hardware truth:
S1 items carry the Checker message and a code excerpt only; S2 items carry a security digest of the plugin (manifest, file list, every line that executes a command,
touches the network, deletes/writes outside the plugin, evals or elevates). Nothing here is a label; panel output is provisional triage.

usage: python3 build_panel_items.py --s1 s1/s1_hw_items.jsonl --s2 s2-pkg/s2_candidates.jsonl --out items.jsonl [--seed 7 --s1-load-fa 120 --s1-bin-present 126 --s1-bin-absent 100]
"""
import argparse
import json
import os
import random
import re

SWEEP = "/workspace/usuba-model-checker/dell/sweep"
RISK = re.compile(r"Process\s*\{|execDetached|command\s*:|exec\(|execute\(|os\.system|subprocess|Popen|\beval\b|\bsudo\b|pkexec|\bcurl\b|\bwget\b|XMLHttpRequest|fetch\(|https?://|\brm\s+-|\brmdir\b|\bdd\b\s+if|mkfs|chmod|chown|\bssh\b|\bscp\b|base64|/etc/|~/\.ssh|\.ssh/|\.gnupg|/dev/|systemctl|dbus|hyprctl\s+dispatch|FileView|writeFile|WRITE|open\([^)]*['\"]w|>\s*~|>>|\bsh\s+-c|bash\s+-c|\bnc\b|socat|token|password|secret|apikey|api_key|Authorization", re.I)


def tree_files(d, cap=300_000):
    out, n = {}, 0
    for r, ds, fs in os.walk(d):
        ds[:] = sorted(x for x in ds if x not in (".git", "node_modules"))
        for f in sorted(fs):
            p = os.path.join(r, f)
            if os.path.islink(p) or os.path.getsize(p) > 150_000:
                continue
            try:
                out[os.path.relpath(p, d)] = open(p, encoding="utf-8").read()
            except (OSError, UnicodeDecodeError):
                continue
            n += len(out[os.path.relpath(p, d)])
            if n > cap:
                return out
    return out


def s2_digest(root, budget=8000):
    files = tree_files(root)
    parts = ["FILES: " + ", ".join(f"{p}({len(t.splitlines())}l)" for p, t in list(files.items())[:60])]
    m = files.get("manifest.json")
    if m:
        parts.append("MANIFEST:\n" + m[:700])
    lines = []
    for p, t in files.items():
        if p.lower().endswith((".md", ".txt", ".svg", ".json", ".license")) or p.lower().startswith("license"):
            continue
        for i, line in enumerate(t.splitlines(), 1):
            if RISK.search(line):
                lines.append(f"{p}:{i}: {line.strip()[:200]}")
    used = sum(len(x) for x in parts)
    keep, total = [], used
    for ln in lines:
        if total + len(ln) > budget:
            keep.append(f"... ({len(lines) - len(keep)} more risky-pattern lines not shown)")
            break
        keep.append(ln)
        total += len(ln) + 1
    parts.append(f"RISKY-PATTERN LINES ({len(lines)} total):\n" + ("\n".join(keep) if keep else "(none)"))
    return "\n\n".join(parts), len(lines)


FILE_IN_MSG = re.compile(r"(?:^|\]\s*|\s)([\w./-]+\.(?:qml|js|sh|py|json|lua))\b")


def s1_excerpt(root, msgs, budget=3500):
    names = []
    for m in msgs:
        for g in FILE_IN_MSG.findall(m):
            if g not in names:
                names.append(g)
    for rel in names[:2]:
        for cand in (rel, os.path.basename(rel)):
            p = os.path.join(root, cand)
            if os.path.isfile(p):
                try:
                    t = open(p, encoding="utf-8", errors="replace").read()
                except OSError:
                    continue
                m = re.search(r"line (\d+)", " ".join(msgs))
                if m:
                    ln = int(m.group(1))
                    seg = t.splitlines()[max(0, ln - 25): ln + 25]
                    return f"{rel} (lines around {ln}):\n" + "\n".join(seg)[:budget]
                return f"{rel} (head):\n" + t[:budget]
    return "(no file excerpt available)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--s1", required=True)
    ap.add_argument("--s2", required=True)
    ap.add_argument("--s2-tree-root", default="/workspace/janus/s2-pkg/stage/plugins")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--s1-load-fa", type=int, default=120)
    ap.add_argument("--s1-bin-present", type=int, default=126)
    ap.add_argument("--s1-bin-absent", type=int, default=100)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    corpus = {}
    for line in open(f"{SWEEP}/corpus.jsonl"):
        c = json.loads(line)
        corpus[c["key"]] = c.get("local_dir")
    s1 = [json.loads(line) for line in open(a.s1)]
    pick = [i for i in s1 if i["group"] == "LOAD" and i["hw_label"] == "real_hw"]
    for grp, lab, n in (("LOAD", "no_symptom_hw", a.s1_load_fa), ("BIN", "present_hw", a.s1_bin_present), ("BIN", "absent_hw", a.s1_bin_absent)):
        L = [i for i in s1 if i["group"] == grp and i["hw_label"] == lab]
        rng.shuffle(L)
        pick += L[:n]
    items = []
    for i in pick:
        root = corpus.get(i["plugin"]) or ""
        items.append(dict(id=i["id"], kind="S1", plugin=i["plugin"], rule=i["category"], claim="Checker finding: " + " | ".join(i["checker_messages"])[:700], context=s1_excerpt(root, i["checker_messages"])))
    n2 = 0
    for line in open(a.s2):
        c = json.loads(line)
        dg, nr = s2_digest(os.path.join(a.s2_tree_root, c["job"]))
        items.append(dict(id="s2:" + c["plugin_id"], kind="S2", plugin=c["repo"], context=dg, evidence="static Checker flags: " + ",".join(c["checker_flags"]) if c["checker_flags"] else ""))
        n2 += 1
    with open(a.out, "w") as f:
        f.writelines(json.dumps(x) + "\n" for x in items)
    print(f"S1 items {len(pick)}  S2 items {n2}  -> {a.out}")


if __name__ == "__main__":
    main()
