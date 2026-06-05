#!/usr/bin/env bash
#
# Run plain Cardumen on every active bug in Defects4J v2.0, in parallel.
#
# Each bug gets its own directory under $RESULTS_ROOT containing:
#   <Project>-<Version>/checkout/      the defects4j working copy
#   <Project>-<Version>/astor-output/  Astor's output (AstorMain-<id>/ inside)
#   <Project>-<Version>/run.log        full stdout/stderr of the run
#   <Project>-<Version>/.done          marker written on success (run is skipped if present)
#
# Usage:
#   ./runAllD4JCardumen.sh [parallelism] [Project ...]
#
#   parallelism   number of bugs to run concurrently (default 4)
#   Project ...   optional list of projects to restrict to (default: all 17)
#
# Examples:
#   ./runAllD4JCardumen.sh 8                 # all bugs, 8 at a time
#   ./runAllD4JCardumen.sh 4 Math Lang       # only Math and Lang bugs, 4 at a time
#   MAXTIME=20 RESULTS_ROOT=/data/d4j ./runAllD4JCardumen.sh 16
#   FORCE=1 ./runAllD4JCardumen.sh 8 Chart   # re-run even bugs already marked .done
#
# Env overrides (also forwarded to runD4JBug.sh):
#   RESULTS_ROOT  where per-bug directories are created (default ./d4j-cardumen-results)
#   MAXTIME       per-bug Astor time budget in minutes (default from runD4JBug.sh: 60)
#   JAVA_LEVEL    -javacompliancelevel (default 8)
#   STOPFIRST     stop each bug once the 1st patch is found (default true; set false to keep searching)
#   FORCE=1       ignore existing .done markers and re-run

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
RUN_ONE="$SCRIPT_DIR/runD4JBug.sh"

D4J_BIN=${D4J_BIN:-$HOME/thesis/defects4j-2.0/framework/bin}
DEFECTS4J="$D4J_BIN/defects4j"
RESULTS_ROOT=${RESULTS_ROOT:-./d4j-cardumen-results}

# --- worker mode: invoked by xargs once per bug -----------------------------
# Runs a single bug with its own output/checkout/log directories, then marks it done.
if [ "${1:-}" = "--worker" ]; then
    project=$2
    version=$3
    id="${project}-${version}"
    bugdir="$RESULTS_ROOT/$id"
    mkdir -p "$bugdir"

    if [ -z "${FORCE:-}" ] && [ -f "$bugdir/.done" ]; then
        echo "[skip] $id (already done)"
        exit 0
    fi

    echo "[start] $id"
    # Per-bug isolation: separate checkout root and Astor output dir.
    if OUT="$bugdir/astor-output" WORK_ROOT="$bugdir/checkout" \
           "$RUN_ONE" "$project" "$version" cardumen > "$bugdir/run.log" 2>&1; then
        touch "$bugdir/.done"
        echo "[ok]   $id"
    else
        rc=$?
        echo "[fail] $id (exit $rc; see $bugdir/run.log)"
        # Astor exits non-zero when no patch is found, which is a normal outcome,
        # so do not abort the whole batch on a single failure.
    fi
    exit 0
fi

# --- main: enumerate bugs and dispatch in parallel --------------------------
N=${1:-4}
case "$N" in
    ''|*[!0-9]*) echo "Error: parallelism must be a positive integer, got '$N'" >&2; exit 2 ;;
esac
[ "$N" -ge 1 ] || { echo "Error: parallelism must be >= 1" >&2; exit 2; }
shift || true
PROJECTS=("$@")   # empty => all projects

[ -x "$DEFECTS4J" ] || { echo "Error: defects4j not found at $DEFECTS4J" >&2; exit 1; }
[ -x "$RUN_ONE" ]   || { echo "Error: runD4JBug.sh not found/executable at $RUN_ONE" >&2; exit 1; }

if [ "${#PROJECTS[@]}" -eq 0 ]; then
    mapfile -t PROJECTS < <("$DEFECTS4J" pids 2>/dev/null)
fi

mkdir -p "$RESULTS_ROOT"
TASKS=$(mktemp)
trap 'rm -f "$TASKS"' EXIT

for p in "${PROJECTS[@]}"; do
    # bids prints numeric ids on stdout (a harmless Perl warning may go to stderr).
    while read -r b; do
        [ -n "$b" ] && printf '%s %s\n' "$p" "$b" >> "$TASKS"
    done < <("$DEFECTS4J" bids -p "$p" 2>/dev/null | grep -E '^[0-9]+$')
done

total=$(wc -l < "$TASKS")
echo ">> ${total} bugs across ${#PROJECTS[@]} project(s): ${PROJECTS[*]}"
echo ">> running ${N} in parallel; results under $RESULTS_ROOT"

# One worker invocation per "Project Version" line, N concurrent.
# bash -c forwards the two line tokens as $1 $2 to the worker.
xargs -P "$N" -L1 bash -c '"$0" --worker "$@"' "$SCRIPT_DIR/runAllD4JCardumen.sh" < "$TASKS"

done_count=$(find "$RESULTS_ROOT" -maxdepth 2 -name .done | wc -l)
echo ">> finished. ${done_count}/${total} bugs completed successfully (have .done markers)."
echo ">> per-bug logs: $RESULTS_ROOT/<Project>-<Version>/run.log"
