#!/usr/bin/env python3
"""Pre-publication scan for this repository: working tree AND full git history. Exit code 1 on any finding.

Checks (patterns only; matched values are never printed, only file, commit and rule name):
  1. credential-shaped strings (API keys, tokens, JWTs, private keys, URL credentials, long key assignments)
  2. home-directory paths other than the neutral placeholders (/home/user/...)
  3. file names of private evaluation/device material (answer keys, labels, raw model outputs, device captures, raw review dumps)
  4. blobs larger than 20 MB, Git LFS pointer files

Run:  python3 tools/scan_public.py [--no-history]
"""
import re, subprocess, sys

SELF = "tools/scan_public.py"
CRED = {
    "openrouter-key": r"sk-or-v1-[A-Za-z0-9]{16,}",
    "anthropic-key": r"sk-ant-[A-Za-z0-9_-]{16,}",
    "openai-style-key": r"\bsk-[A-Za-z0-9]{32,}\b",
    "github-token": r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}",
    "huggingface-token": r"\bhf_[A-Za-z0-9]{30,}\b",
    "aws-key-id": r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b",
    "google-api-key": r"\bAIza[0-9A-Za-z_-]{35}\b",
    "slack-token": r"\bxox[baprs]-[A-Za-z0-9-]{10,}",
    "stripe-key": r"\b(?:sk|rk)_live_[A-Za-z0-9]{16,}",
    "private-key-block": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "jwt": r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*",
    "bearer-token": r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{24,}",
    "url-credentials": r"(?i)\b[a-z][a-z0-9+.-]*://[^\s/:@'\"]{2,}:[^\s/:@'\"]{4,}@(?!localhost|example)[A-Za-z0-9.-]+",
    "key-assignment": r"(?i)\b(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|password)\b[\"']?\s*[:=]\s*[\"'][A-Za-z0-9/+_=-]{24,}[\"']",
}
NEUTRAL_HOMES = {"user", "runner", "username", "you", "me", "name", "foo", "someone", "example", "alice", "bob", "$USER", "USER", "<user>"}
HOME = re.compile(r"/home/([A-Za-z0-9_.$<>-]+)/")
PRIVATE_NAMES = re.compile(r"(?i)(dell_ground_truth|(^|/)labels_(draft|final)|ground_truth_(rows|additions)|dellkey.*\.(raw|reason)|\.raw\.jsonl$|\.reason\.json$|(^|/)teacher-|dell-capture/|(^|/)dell/|dell_rounds/|dell-batch|dell-smoke|(^|/)\.env(\.|$)|\.pem$|id_rsa|hancore_labels|data/reviews/|hancore_reviewer/|hancore_holdout/(manifest\.jsonl|code/))")
ALLOW_ABS = {"/home/user", "/home/runner"}


def sh(*a, **k):
    return subprocess.run(a, capture_output=True, **k)


def scan_text(label, path, text, out):
    for rule, rx in CRED.items():
        if re.search(rx, text):
            out.append((label, path, rule))
    for m in HOME.finditer(text):
        if m.group(1) not in NEUTRAL_HOMES:
            out.append((label, path, "home-path"))
            break


def main():
    history = "--no-history" not in sys.argv
    out = []
    files = sh("git", "ls-files", "-z").stdout.decode().split("\0")
    for f in filter(None, files):
        if f == SELF:
            continue
        if PRIVATE_NAMES.search(f):
            out.append(("tree", f, "private-file-name"))
            continue
        try:
            data = open(f, "rb").read()
        except OSError:
            continue
        if data.startswith(b"version https://git-lfs"):
            out.append(("tree", f, "lfs-pointer"))
        if b"\0" in data[:8192]:
            continue
        scan_text("tree", f, data.decode("utf-8", "replace"), out)
    if history:
        # every distinct blob in history, once
        objs = sh("git", "rev-list", "--objects", "--all").stdout.decode().splitlines()
        batch = sh("git", "cat-file", "--batch-check=%(objecttype) %(objectname) %(objectsize) %(rest)", input="\n".join(o.split()[0] for o in objs).encode()).stdout.decode().splitlines()
        names = {}
        for o in objs:
            p = o.split(" ", 1)
            names[p[0]] = p[1] if len(p) > 1 else ""
        todo = []
        for line in batch:
            t, h, size, *_ = line.split(" ")
            if t != "blob":
                continue
            p = names.get(h, "")
            if p == SELF:
                continue
            if int(size) > 20_000_000:
                out.append(("history", p, "blob>20MB"))
            if PRIVATE_NAMES.search(p):
                out.append(("history", p, "private-file-name"))
                continue
            todo.append((h, p))
        proc = subprocess.Popen(["git", "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        for h, p in todo:
            proc.stdin.write((h + "\n").encode()); proc.stdin.flush()
            hdr = proc.stdout.readline().split()
            n = int(hdr[2]); data = proc.stdout.read(n); proc.stdout.read(1)
            if data.startswith(b"version https://git-lfs"):
                out.append(("history", p, "lfs-pointer"))
            if b"\0" in data[:8192]:
                continue
            scan_text("history", p, data.decode("utf-8", "replace"), out)
        proc.stdin.close(); proc.wait()
        # commit metadata: only the maintainer's addresses may appear
        emails = set(sh("git", "log", "--all", "--format=%ae%n%ce").stdout.decode().split())
        for e in emails:
            if not (e.endswith("@users.noreply.github.com") or e.endswith("@outboundsync.com")):
                out.append(("history", "commit-metadata", "unexpected-author-email"))
    seen = set()
    for label, path, rule in out:
        k = (label, path, rule)
        if k in seen:
            continue
        seen.add(k)
        print(f"FINDING {label} {path} {rule}")
    print(f"scan_public: {len(seen)} finding(s)")
    sys.exit(1 if seen else 0)


if __name__ == "__main__":
    main()
