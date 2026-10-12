#!/usr/bin/env python3
"""Calibration: known-good public community plugins must PASS, dell-smoke model junk must FAIL."""
import json, os, sys
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import functest
R = "/workspace/omarchy-specialist/sources/repos"
GOOD = {  # public repos, all listed in the omarchyplugins.com catalog snapshot (sources/catalog.json)
  "jankeesvw.time-machine": f"{R}/jankeesvw.time-machine", "robzolkos.github": f"{R}/robzolkos.github",
  "crmne.omastats": f"{R}/crmne.omastats", "crmne.mpris": f"{R}/crmne.mpris",
  "jankeesvw.notification-center": f"{R}/jankeesvw.notification-center", "tahayvr.postcard": f"{R}/tahayvr.postcard",
  "io.github.tyrichards.tray": f"{R}/io.github.tyrichards.tray", "akshar.radio-atlas": f"{R}/akshar.radio-atlas",
  "com.omastorm.radar": f"{R}/com.omastorm.radar", "njpatel.omapager": f"{R}/njpatel.omapager",
  "crmne.hyprmoncfg": f"{R}/crmne.hyprmoncfg", "salted.bar": f"{R}/salted.bar", "jankeesvw.clippy": f"{R}/jankeesvw.clippy",
  "zeru.portwatch": f"{R}/zeru.portwatch", "tornikegomareli.spaces": f"{R}/tornikegomareli.spaces",
  # real upstream versions of the ids the model hallucinated in dell-smoke
  "sanjyay.peekbar(real)": f"{R}/sanjyay.peekbar", "scottjones.flush-bar(real)": f"{R}/scottjones.flush-bar",
  "vimarchy(real)": f"{R}/vimarchy", "fkcodes.key-promoter(real)": f"{R}/fkcodes.key-promoter",
  # bobbynicholas.omaland(real) is a deliberate ~/.config/hypr/looknfeel.lua editor: rejected BY POLICY, tracked separately

  # Harris's own published plugins (github.com/kenhara/*)
  "kenhara.rocketlauncher": "/workspace/omarchy-rocketlauncher", "kenhara.compliantish": "/workspace/omarchy-compliantish",
  "kenhara.enricherino": "/workspace/omarchy-enricherino", "kenhara.encyclopedic": "/workspace/omarchy-encyclopedic",
  "kenhara.scriptural": "/workspace/omarchy-scriptural",
}
D = "/workspace/omarchy-specialist/dell-smoke"
BAD = {n: f"{D}/{n}" for n in sorted(os.listdir(D)) if os.path.isdir(f"{D}/{n}")}
POLICY = {"bobbynicholas.omaland(real, hypr editor)": f"{R}/bobbynicholas.omaland"}
def one(item):
    name, path, expect = item
    r = functest.test(src_dir=path)
    return name, expect, r
if __name__ == "__main__":
    only = sys.argv[1:]
    items = [(n, p, "pass") for n, p in GOOD.items()] + [(n, p, "fail") for n, p in BAD.items()] + [(n, p, "fail") for n, p in POLICY.items()]
    if only: items = [i for i in items if any(o in i[0] for o in only)]
    out = {}
    with ThreadPoolExecutor(6) as ex:
        for name, expect, r in ex.map(one, items):
            ok = (r["pass"] and expect == "pass") or (not r["pass"] and expect == "fail")
            out[name] = dict(expect=expect, got="pass" if r["pass"] else "fail", correct=ok, categories=r["categories"],
                             static_fails=r["static_fails"], runtime_errors=(r["runtime"] or {}).get("errors"),
                             runtime_checks=(r["runtime"] or {}).get("checks"), soft=(r["runtime"] or {}).get("soft", [])[:3])
            print(("OK  " if ok else "MISS"), expect, name, r["categories"], flush=True)
    json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "calibration.json" if not only else "calibration_partial.json"), "w"), indent=1)
