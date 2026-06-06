#!/usr/bin/env bash
#
# Run Cardumen on every active bug in Defects4J v2.0, in parallel.
#
# Two repair engines are selectable via --engine (default: cardumen):
#   cardumen   plain Cardumen template-based repair
#   export     CardumenExportEngine (-customengine ...) + Julia find2fix.jl tool
#
# Each bug gets its own directory under $RESULTS_ROOT containing:
#   <Project>-<Version>/checkout/      the defects4j working copy
#   <Project>-<Version>/astor-output/  Astor's output (AstorMain-<id>/ inside)
#   <Project>-<Version>/run.log        full stdout/stderr of the run
#   <Project>-<Version>/.done          marker written on success (run is skipped if present)
#   <Project>-<Version>/.error         marker written on failure, holds the exit code
#                                       (run is skipped if present; not written for exit 130/Ctrl+C)
#
# Usage:
#   ./runAllD4JCardumen.sh [--engine export|cardumen] [parallelism] [Project ...]
#
#   --engine, -e  repair engine: 'cardumen' (default) or 'export'. May also be set
#                 via the ENGINE env var; the flag wins if both are given.
#   parallelism   number of bugs to run concurrently (default 4)
#   Project ...   optional list of projects to restrict to (default: all 17)
#
# Examples:
#   ./runAllD4JCardumen.sh 8                  # all bugs, 8 at a time, plain cardumen
#   ./runAllD4JCardumen.sh 4 Math Lang        # only Math and Lang bugs, 4 at a time
#   ./runAllD4JCardumen.sh --engine export 8  # all bugs via CardumenExportEngine
#   ./runAllD4JCardumen.sh -e export 4 Math   # export engine on Math, 4 at a time
#   MAXTIME=20 RESULTS_ROOT=/data/d4j ./runAllD4JCardumen.sh 16
#   FORCE=1 ./runAllD4JCardumen.sh 8 Chart    # re-run even bugs already marked .done
#
# The 'export' engine honors the JULIA_TOOL / JULIA_PROJECT env vars (read by
# runD4JBug.sh, which warns and falls back to constant '0' if the tool is missing).
#
# Env overrides (also forwarded to runD4JBug.sh):
#   ENGINE        repair engine (default cardumen); overridden by --engine/-e
#   RESULTS_ROOT  where per-bug directories are created
#                 (default ./d4j-cardumen-results, or ./d4j-cardumen-export-results
#                  when --engine export is used)
#   MAXTIME       per-bug Astor time budget in minutes (default from runD4JBug.sh: 60)
#   JAVA_LEVEL    -javacompliancelevel (default 8)
#   STOPFIRST     stop each bug once the 1st patch is found (default true; set false to keep searching)
#   FORCE=1       ignore existing .done markers and re-run
#   REAP          run the orphaned-test-JVM reaper (default true; set false to disable)
#   REAP_AGE      kill orphaned test JVMs older than this many seconds (default 660;
#                 must exceed Astor's per-validation timeout tmax2, default 600s)
#   REAP_INTERVAL seconds between reaper sweeps (default 60)

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
RUN_ONE="$SCRIPT_DIR/runD4JBug.sh"

D4J_BIN=${D4J_BIN:-$HOME/thesis/defects4j-2.0/framework/bin}
DEFECTS4J="$D4J_BIN/defects4j"
REAP=${REAP:-true}
REAP_AGE=${REAP_AGE:-660}
REAP_INTERVAL=${REAP_INTERVAL:-60}

# Safety-net reaper: Astor forks a 2GB test JVM per candidate validation and, on a
# timeout, can fail to kill it (orphaning it). Even with the source-level fix this
# periodically sweeps any test JVM that outlived its validation timeout. It targets
# ONLY Astor's JUnit executor processes (never the AstorMain repair process) and only
# those older than REAP_AGE, so in-flight validations are never touched.
reaper_loop() {
    local parent=$1   # orchestrator PID; self-exit if it dies (covers kill -9, where traps can't run)
    while true; do
        sleep "$REAP_INTERVAL"
        kill -0 "$parent" 2>/dev/null || exit 0   # orchestrator gone -> stop reaping
        pids=$(ps -eo pid=,etimes=,args= 2>/dev/null | awk -v age="$REAP_AGE" '
            $0 ~ /JUnit(Nolog)?ExternalExecutor/ && $0 !~ /AstorMain/ && ($2+0) > age { print $1 }
        ')
        if [ -n "$pids" ]; then
            n=$(printf '%s\n' "$pids" | wc -l)
            printf '%s\n' "$pids" | xargs -r kill -9 2>/dev/null || true
            echo "[reaper $(date +%H:%M:%S)] killed $n orphaned test JVM(s)"
        fi
    done
}
# Engine + results-root resolution.
# In worker mode the engine arrives via the exported ENGINE env var; in main mode it
# may be overridden by --engine/-e (parsed below, which re-runs resolve_results_root).
RESULTS_ROOT_ENV=${RESULTS_ROOT:-}      # capture an explicit user override, if any
ENGINE=${ENGINE:-cardumen}
resolve_results_root() {                # default depends on the engine; override wins
    if [ -n "$RESULTS_ROOT_ENV" ]; then
        RESULTS_ROOT=$RESULTS_ROOT_ENV
    elif [ "$ENGINE" = export ]; then
        RESULTS_ROOT=./d4j-cardumen-export-results
    else
        RESULTS_ROOT=./d4j-cardumen-results
    fi
}
resolve_results_root

# --- worker mode: invoked by xargs once per bug -----------------------------
# Runs a single bug with its own output/checkout/log directories, then marks it done.
if [ "${1:-}" = "--worker" ]; then
    project=$2
    version=$3
    index=${4:-?}                       # this bug's position in the task list (for the log prefix)
    id="${project}-${version}"
    bugdir="$RESULTS_ROOT/$id"
    mkdir -p "$bugdir"

    # Prefix every per-bug line with a timestamp and "<index>/<total>" progress counter.
    # TOTAL is exported by the main process; ? is a fallback for manual --worker calls.
    log() { printf '%s %s/%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$index" "${TOTAL:-?}" "$*"; }

    if [ -z "${FORCE:-}" ] && { [ -f "$bugdir/.done" ] || [ -f "$bugdir/.error" ]; }; then
        log "[skip] $id (already attempted)"
        exit 0
    fi

    log "[start] $id"
    # Per-bug isolation: separate checkout root and Astor output dir.
    if OUT="$bugdir/astor-output" WORK_ROOT="$bugdir/checkout" \
           "$RUN_ONE" "$project" "$version" "$ENGINE" > "$bugdir/run.log" 2>&1; then
        rm -f "$bugdir/.error"          # clear any stale marker from a prior FORCE run
        touch "$bugdir/.done"
        log "[ok]   $id"
    else
        rc=$?
        # Astor exits non-zero when no patch is found, which is a normal outcome,
        # so do not abort the whole batch on a single failure.
        if [ "$rc" -eq 130 ]; then
            # 130 = terminated by SIGINT (Ctrl+C); not a real outcome, leave unmarked.
            log "[int]  $id (interrupted, exit 130; no marker written)"
        else
            rm -f "$bugdir/.done"       # clear any stale marker from a prior FORCE run
            echo "$rc" > "$bugdir/.error"
            log "[fail] $id (exit $rc; see $bugdir/run.log)"
        fi
    fi
    exit 0
fi

# --- main: enumerate bugs and dispatch in parallel --------------------------
# Parse leading --engine/-e options before the parallelism positional.
while [ $# -gt 0 ]; do
    case "$1" in
        -e|--engine) [ $# -ge 2 ] || { echo "Error: $1 requires a value" >&2; exit 2; }
                     ENGINE=$2; shift 2 ;;
        --engine=*)  ENGINE=${1#*=}; shift ;;
        --)          shift; break ;;
        -*)          echo "Error: unknown option '$1'" >&2; exit 2 ;;
        *)           break ;;
    esac
done
case "$ENGINE" in
    export|cardumen) ;;
    *) echo "Error: engine must be 'export' or 'cardumen', got '$ENGINE'" >&2; exit 2 ;;
esac
resolve_results_root   # re-resolve in case --engine changed the engine

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

# Start the reaper and ensure it (and the temp file) are cleaned up on exit.
REAPER_PID=""
if [ "$REAP" = "true" ]; then
    reaper_loop "$$" &        # pass our PID so the reaper self-exits if we die
    REAPER_PID=$!
    echo ">> reaper on: sweeping orphaned test JVMs older than ${REAP_AGE}s every ${REAP_INTERVAL}s"
fi
# Kill the reaper promptly on normal exit and on common termination signals.
# (SIGKILL can't be trapped, but the reaper also watches our PID and self-exits.)
cleanup() { [ -n "$REAPER_PID" ] && kill "$REAPER_PID" 2>/dev/null; rm -f "$TASKS"; }
trap cleanup EXIT
trap 'cleanup; exit 130' INT
trap 'cleanup; exit 143' TERM HUP

# Each task line is "Project Version Index", where Index is the bug's 1-based
# position across all enumerated bugs. Workers echo it as "<Index>/<TOTAL>".
idx=0
for p in "${PROJECTS[@]}"; do
    # bids prints numeric ids on stdout (a harmless Perl warning may go to stderr).
    while read -r b; do
        [ -n "$b" ] || continue
        idx=$((idx + 1))
        printf '%s %s %s\n' "$p" "$b" "$idx" >> "$TASKS"
    done < <("$DEFECTS4J" bids -p "$p" 2>/dev/null | grep -E '^[0-9]+$')
done

total=$(wc -l < "$TASKS")
export TOTAL="$total"          # forwarded to workers for the "<index>/<total>" log prefix
export ENGINE                  # so each xargs worker uses the chosen engine
export RESULTS_ROOT            # so workers inherit the resolved results directory
echo ">> ${total} bugs across ${#PROJECTS[@]} project(s): ${PROJECTS[*]}"
echo ">> engine=${ENGINE}; running ${N} in parallel; results under $RESULTS_ROOT"

# One worker invocation per "Project Version" line, N concurrent.
# bash -c forwards the two line tokens as $1 $2 to the worker.
xargs -P "$N" -L1 bash -c '"$0" --worker "$@"' "$SCRIPT_DIR/runAllD4JCardumen.sh" < "$TASKS"

done_count=$(find "$RESULTS_ROOT" -maxdepth 2 -name .done | wc -l)
error_count=$(find "$RESULTS_ROOT" -maxdepth 2 -name .error | wc -l)
echo ">> finished. ${done_count}/${total} bugs completed successfully (have .done markers); ${error_count} failed (have .error markers)."
echo ">> per-bug logs: $RESULTS_ROOT/<Project>-<Version>/run.log"
