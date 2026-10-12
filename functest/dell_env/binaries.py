"""Executable resolution against the real Dell Omarchy Quattro install."""
import os, re
HERE = os.path.dirname(os.path.abspath(__file__))
OMARCHY_BINS = {l.strip() for l in open(os.path.join(HERE, "omarchy_bins.txt")) if l.strip()}
SYSTEM_BINS = {w for l in open(os.path.join(HERE, "system_bins.txt")) if not l.startswith("#") for w in l.split()}
KNOWN = OMARCHY_BINS | SYSTEM_BINS
ABS_OK = re.compile(r"^/(usr/)?(s?bin)/")
def resolves(cmd, plugin_files=(), plugin_dir=None):
    """True if argv[0] would start on the Dell. plugin_files: relpaths the plugin ships."""
    c = str(cmd or "")
    if not c: return False
    if c.startswith("/"):
        if plugin_dir and c.startswith(plugin_dir.rstrip("/") + "/"): return True
        if "/.config/omarchy/plugins/" in c: return True
        if c.startswith("/usr/share/omarchy/bin/") or c.startswith("/opt/ft/"): return os.path.basename(c) in OMARCHY_BINS or c.startswith("/opt/ft/")
        if ABS_OK.match(c): return os.path.basename(c) in KNOWN
        return False
    if "/" in c:   # relative path: must be shipped by the plugin
        return c.lstrip("./") in plugin_files
    return c in KNOWN   # a bare name must be on the Dell PATH; plugin-shipped scripts are not
