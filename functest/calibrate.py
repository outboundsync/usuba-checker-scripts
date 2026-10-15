#!/usr/bin/env python3
"""Calibration: known-good public community plugins must PASS, known-bad (model-generated junk) plugins must FAIL.

Inputs are not stored in this repository:
  FT_CALIB_REPOS  directory with the good plugins checked out by id (default ../usuba-checker-models/sources/repos, filled by
                  `python3 sources/fetch_plugin_sources.py` in the models repo)
  FT_CALIB_BAD    optional directory of known-bad plugin dirs that must FAIL (the original smoke-test junk is private; supply your own)
Missing plugin dirs are skipped with a note, so the script runs with whatever you have."""
import json, os, sys
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import functest
HERE = os.path.dirname(os.path.abspath(__file__))
R = os.environ.get("FT_CALIB_REPOS") or os.path.normpath(os.path.join(HERE, "..", "..", "usuba-checker-models", "sources", "repos"))
GOOD = {  # public repos, all listed in the omarchyplugins.com catalog snapshot (sources/catalog.json)
  "jankeesvw.time-machine": f"{R}/jankeesvw.time-machine", "robzolkos.github": f"{R}/robzolkos.github",
  "crmne.omastats": f"{R}/crmne.omastats", "crmne.mpris": f"{R}/crmne.mpris",
  "jankeesvw.notification-center": f"{R}/jankeesvw.notification-center", "tahayvr.postcard": f"{R}/tahayvr.postcard",
  "io.github.tyrichards.tray": f"{R}/io.github.tyrichards.tray", "akshar.radio-atlas": f"{R}/akshar.radio-atlas",
  "com.omastorm.radar": f"{R}/com.omastorm.radar", "njpatel.omapager": f"{R}/njpatel.omapager",
  "crmne.hyprmoncfg": f"{R}/crmne.hyprmoncfg", "salted.bar": f"{R}/salted.bar", "jankeesvw.clippy": f"{R}/jankeesvw.clippy",
  "zeru.portwatch": f"{R}/zeru.portwatch", "tornikegomareli.spaces": f"{R}/tornikegomareli.spaces",
  # real upstream versions of ids that model-generated junk used to hallucinate
  "sanjyay.peekbar(real)": f"{R}/sanjyay.peekbar", "scottjones.flush-bar(real)": f"{R}/scottjones.flush-bar",
  "vimarchy(real)": f"{R}/vimarchy", "fkcodes.key-promoter(real)": f"{R}/fkcodes.key-promoter",
  # bobbynicholas.omaland(real) is a deliberate ~/.config/hypr/looknfeel.lua editor: rejected BY POLICY, tracked separately

  # Harris's own published plugins (github.com/kenhara/*)
  "kenhara.rocketlauncher": f"{R}/kenhara.rocketlauncher", "kenhara.compliantish": f"{R}/kenhara.compliantish",
  "kenhara.enricherino": f"{R}/kenhara.enricherino", "kenhara.encyclopedic": f"{R}/kenhara.encyclopedic",
  "kenhara.scriptural": f"{R}/kenhara.scriptural",
}
D = os.environ.get("FT_CALIB_BAD")
BAD = {n: f"{D}/{n}" for n in sorted(os.listdir(D)) if os.path.isdir(f"{D}/{n}")} if D and os.path.isdir(D) else {}
POLICY = {"bobbynicholas.omaland(real, hypr editor)": f"{R}/bobbynicholas.omaland"}
def one(item):
    name, path, expect = item
    r = functest.test(src_dir=path)
    return name, expect, r
if __name__ == "__main__":
    only = sys.argv[1:]
    items = [(n, p, "pass") for n, p in GOOD.items()] + [(n, p, "fail") for n, p in BAD.items()] + [(n, p, "fail") for n, p in POLICY.items()]
    missing = [i[0] for i in items if not os.path.isdir(i[1])]
    if missing: print(f"skipping {len(missing)} plugin(s) not found (set FT_CALIB_REPOS / FT_CALIB_BAD): {missing[:5]}...", file=sys.stderr)
    items = [i for i in items if os.path.isdir(i[1])]
    if not items: sys.exit('nothing to calibrate: no plugin dirs found')
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
