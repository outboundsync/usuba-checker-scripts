#!/usr/bin/env python3
"""Checks learned from the Dell hardware sweep (dell/sweep/DELL_LEARNINGS.md). check(files) -> usuba-style findings
(dict(rule, severity, file, reason, hint)); severity "high" blocks, "medium"/"low" warn. Levels follow the precision each
check reached against Dell labels (see DELL_LEARNINGS.md, "New checks").
  USB-D01 system-audio-graph-mutation : rewires the user's global PipeWire/Pulse graph (default sink, filter nodes,
          loopbacks). One such plugin (pennyfx.audio-control) set off the desktop-shell socket storm that ended in a
          13 GB OOM kill on the Dell (17:32:34-17:50:27, 2026-10-13).
  USB-D02 toggle-entry-without-handler : a panel/overlay entry point exposes no toggle()/open()/show() function, so the
          shell's IPC toggle has nothing to call; on the Dell such plugins opened no surface after `shell toggle`.
  (A static respawn-loop heuristic was evaluated and dropped: 0/88 hits matched Dell memory/CPU growth. Runaway memory is
   measured at runtime instead: USB-D05 in runtime.py; the usage cycle is USB-D04.)
"""
import json, re
AUDIO = re.compile(r"pw-metadata[^\n]*target\.object|pactl\s+(load-module|set-default-(sink|source)|move-sink-input|move-source-output)|wpctl\s+set-default|pw-loopback|\bfilter-chain\b|module-null-sink|module-loopback")
TOGGLE_FN = re.compile(r"\bfunction\s+(toggle|open|show|summon)\s*\(")
TIMER = re.compile(r"Timer\s*\{", re.S)
def _blocks(s, start_re):
    for m in start_re.finditer(s):
        i, depth = m.end(), 1
        while i < len(s) and depth:
            depth += {"{": 1, "}": -1}.get(s[i], 0); i += 1
        yield m.start(), s[m.start():i]
def _strip(s): return re.sub(r"(^|[^:\"'])//[^\n]*", r"\1", s)
def check(files):
    out = []
    try: man = json.loads(files.get("manifest.json", "") or "{}")
    except Exception: man = {}
    if not isinstance(man, dict): man = {}
    for p, body in files.items():
        if p.endswith((".md", ".txt", ".json")): continue
        m = AUDIO.search(_strip(body))
        if m:
            out.append(dict(rule="USB-D01", severity="medium", file=p, reason=f"changes the user's global audio graph (`{m.group(0)[:60]}`); on the Dell this kind of change outlived the plugin and destabilised the desktop shell",
                            hint="scope audio changes to nodes the plugin creates, restore the previous default on exit, never loop on rebuilding nodes, and document the side effect"))
            break
    ep = man.get("entryPoints") if isinstance(man.get("entryPoints"), dict) else {}
    kinds = set(man.get("kinds") or []) if isinstance(man.get("kinds"), list) else set()
    if not (kinds & {"bar", "bar-widget"}):
        for k in ("panel", "overlay"):
            f = ep.get(k)
            if isinstance(f, str) and f in files and not TOGGLE_FN.search(_strip(files[f])):
                # the shell's toggle may also be handled by an IpcHandler or by the shell host (PanelHost) - accept explicit handlers
                if not re.search(r"IpcHandler|onToggle|function\s+\w*[Tt]oggle\w*\s*\(", files[f]):
                    out.append(dict(rule="USB-D02", severity="medium", file=f, reason=f"{k} entry point has no toggle()/open()/show() function, so `shell toggle <id>` has nothing to call",
                                    hint=f"add `function toggle() {{ ... }}` (and open/close) to the {k} root so the shell can summon it"))
    return out
