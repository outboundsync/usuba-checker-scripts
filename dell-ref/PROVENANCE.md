# dell-ref: provenance (audit F6)

- `omarchy-4.0.4/` is a capture of `/usr/share/omarchy` from the reference laptop (Dell) running the Arch package `omarchy 4.0.4-1` (`omarchy-4.0.4-pkgver.txt`). Images are excluded; absolute symlinks into `/usr/bin` are kept as-is and dangle off the device.
- The tree's own `version` file says `4.0.0.alpha` while the package version is 4.0.4-1. The upstream commit that corresponds to the package is **not recorded**; I could not determine it from this repository. When the package is rebuilt from a known tag, record the tag and the package sha256 here.
- `omarchy-4.0.4-tree.tar.gz` (sha256 `3105074581aee019357c1752a99556b9c9f3e0ed38c676780795ee29219b2373`) is **not** a byte-for-byte duplicate of the extracted tree: it additionally contains `default/plymouth/logos` (images). No code reads it. It is kept for that reason; delete it if the images are not wanted.
- Licence: Omarchy is MIT, Copyright (c) David Heinemeier Hansson. The upstream text is in `LICENSE` here (fetched from basecamp/omarchy).
- Use: the Checker's static API tables are built from this tree (`functest/refpaths.py`). The runtime sandbox uses the separately built `/opt/ft/omarchy-4.0.4` (with the ftProbe patch), not this tree.
