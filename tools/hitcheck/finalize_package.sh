#!/bin/bash
# copies the scripts and README next to the tarballs built by build_package.py and writes SHA256SUMS. usage: finalize_package.sh [OUTDIR]
set -e; H=$(cd "$(dirname "$0")" && pwd); OUT=${1:-$PACKAGE_DIR}
cp "$H/run_hitcheck.sh" "$H/hc_signal.py" "$H/analyze_results.py" "$H/README.md" "$OUT/"; chmod +x "$OUT/run_hitcheck.sh"
(cd "$OUT" && sha256sum run_hitcheck.sh hc_signal.py analyze_results.py README.md jobs.json jobs.tsv plugins-A.tar.gz plugins-B.tar.gz > SHA256SUMS)
du -sh "$OUT"
