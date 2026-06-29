#!/usr/bin/env bash
#
# Archive one or more d4j-* results directories with 7-Zip, producing one .zip
# per input directory (e.g. d4j-cardumen-bfs-results -> d4j-cardumen-bfs-results.zip).
#
# The per-bug `checkout/` directories (the defects4j working copies) are EXCLUDED:
# they dominate the archive size and are redundant — the source is identical across
# all bugs of the same project and is recoverable from defects4j. Only the results
# (astor-output/, run.log, .done/.error markers) are archived.
#
# Usage:
#   ./zipResults.sh <d4j-dir> [<d4j-dir> ...]
#
# Examples:
#   ./zipResults.sh d4j-cardumen-bfs-results
#   ./zipResults.sh d4j-cardumen-results d4j-cardumen-bfs-results d4j-cardumen-mlfs-results
#   OUTDIR=/tmp/archives LEVEL=9 ./zipResults.sh d4j-cardumen-mlfs-results
#   FORCE=1 ./zipResults.sh d4j-cardumen-bfs-results      # overwrite existing zip
#
# Env overrides:
#   OUTDIR   directory to write the .zip files into   (default: current directory)
#   LEVEL    7z compression level, 0-9                (default: 5)
#   FORCE    set non-empty to overwrite existing zips (default: refuse)

set -euo pipefail

OUTDIR=${OUTDIR:-.}
LEVEL=${LEVEL:-5}

usage() {
    echo "Usage: $0 <d4j-dir> [<d4j-dir> ...]" >&2
    echo "  Archives each directory to <basename>.zip, excluding 'checkout/' dirs." >&2
    exit 2
}

[ $# -ge 1 ] || usage

command -v 7z >/dev/null 2>&1 || {
    echo "Error: '7z' not found on PATH. Install it (e.g. 'sudo apt install p7zip-full')." >&2
    exit 1
}

mkdir -p "$OUTDIR"

rc=0
for arg in "$@"; do
    dir=${arg%/}   # strip a trailing slash so basename is clean

    if [ ! -d "$dir" ]; then
        echo "Warning: skipping '$arg' (not a directory)" >&2
        rc=1
        continue
    fi

    out="$OUTDIR/$(basename "$dir").zip"

    if [ -e "$out" ] && [ -z "${FORCE:-}" ]; then
        echo "Warning: '$out' already exists; skipping (set FORCE=1 to overwrite)" >&2
        rc=1
        continue
    fi
    rm -f "$out"   # 7z appends to an existing archive; ensure a clean one

    echo ">> Archiving '$dir' -> '$out' (excluding checkout/, level $LEVEL)"
    # -tzip      : ZIP format
    # -mx=$LEVEL : compression level
    # -mmt       : multithreaded compression
    # -xr!checkout : recursively exclude any directory named 'checkout' (and contents)
    7z a -tzip -mx="$LEVEL" -mmt -xr'!checkout' "$out" "$dir"

    size=$(du -h "$out" | cut -f1)
    echo ">> Done: $out ($size)"
done

exit "$rc"
