#!/usr/bin/env bash
#
# Generate one SLURM job script per Defects4J v2.0 bug, per repair mode, for the
# DelftBlue cluster. Each bug/mode runs as its OWN sbatch job so the scheduler can
# interleave them with other users' work (unlike runAllD4JCardumen.sh, which packs
# every bug into a single long-running process).
#
# Modes (same engines as runD4JBug.sh / runAllD4JCardumen.sh):
#   cardumen   plain Cardumen template-based repair        -> d4j-cardumen-results
#   bfs        CardumenExportEngine + Julia, BFS synthesis -> d4j-cardumen-bfs-results
#   mlfs       CardumenExportEngine + Julia, MLFS synthesis-> d4j-cardumen-mlfs-results
#
# Each generated job writes into exactly the directory layout that
# runAllD4JCardumen.sh produces, so generate_results_table.py keeps working:
#   <RESULTS_ROOT>/<Project>-<Version>/checkout/      defects4j working copy
#   <RESULTS_ROOT>/<Project>-<Version>/astor-output/  Astor output (AstorMain-<id>/ inside)
#   <RESULTS_ROOT>/<Project>-<Version>/run.log        full stdout/stderr of the run
#   <RESULTS_ROOT>/<Project>-<Version>/.done          marker written on success
#   <RESULTS_ROOT>/<Project>-<Version>/.error         marker written on failure (holds exit code)
# where RESULTS_ROOT is the per-mode directory listed above.
#
# Usage:
#   ./generate_jobs.sh [--modes "cardumen bfs mlfs"] [Project ...]
#
#   --modes, -m   space-separated modes to generate (default: "cardumen bfs mlfs").
#   Project ...   optional list of projects to restrict to (default: all D4J projects).
#
# Examples:
#   ./generate_jobs.sh                      # all bugs, all 3 modes
#   ./generate_jobs.sh --modes "bfs mlfs"   # only the export-engine modes, all bugs
#   ./generate_jobs.sh -m cardumen Math Lang
#
# Output:
#   $JOBS_DIR/<mode>/<Project>-<Version>.sbatch   one job script per bug/mode
#   $JOBS_DIR/logs/<mode>/                         SLURM stdout/stderr land here
#   $JOBS_DIR/submit_all.sh                        sbatch every generated job (skips .done)
#
# After generating, submit on the cluster with:
#   bash delftblue/jobs/submit_all.sh
#
# Env overrides (baked into each generated job so the run is reproducible on the cluster):
#   ASTOR_ROOT     astor checkout root         (default: parent of this script's dir)
#   ASTOR_JAR      fat jar path                (default: $ASTOR_ROOT/target/astor-2.0.0-jar-with-dependencies.jar)
#   D4J_BIN        defects4j bin dir           (default: /scratch/rrlvandergeest/defects4j/framework/bin)
#   JULIA_TOOL     find2fix.jl path            (default: /scratch/rrlvandergeest/find2fix-herb/find2fix.jl)
#   JULIA_PROJECT  julia project dir           (default: /scratch/rrlvandergeest/find2fix-herb)
#   RESULTS_BASE   dir holding the d4j-cardumen-*-results roots (default: $ASTOR_ROOT)
#   JOBS_DIR       where to write job scripts  (default: <this script's dir>/jobs)
#   MAXTIME        Astor search budget, minutes (default 60)
#   BUFFER         extra minutes added to MAXTIME for the SLURM wall-time (default 20)
#   SLURM_TIME     explicit HH:MM:SS wall-time (default: MAXTIME+BUFFER); overrides BUFFER
#   JAVA_LEVEL     -javacompliancelevel        (default 8)
#   STOPFIRST      stop each bug at 1st patch  (default true)
#   PARTITION      SLURM --partition           (default compute)
#   ACCOUNT        SLURM --account             (default education-eemcs-msc-cs)
#   CPUS           SLURM --cpus-per-task       (default 6)
#   MEM_PER_CPU    SLURM --mem-per-cpu         (default 2G)
#
# Every job loads the 2025, subversion and julia modules (subversion is needed for
# the SVN-backed Chart project; julia for the bfs/mlfs export engines). They are
# loaded unconditionally for all modes to keep the generated jobs uniform.

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

# --- configuration (env-overridable) ----------------------------------------
ASTOR_ROOT=${ASTOR_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}
ASTOR_JAR=${ASTOR_JAR:-$ASTOR_ROOT/target/astor-2.0.0-jar-with-dependencies.jar}
# Defaults point at the DelftBlue cluster layout (where this generator is meant to
# run, since it enumerates bugs via defects4j and bakes these paths into each job).
D4J_BIN=${D4J_BIN:-/scratch/rrlvandergeest/defects4j/framework/bin}
JULIA_TOOL=${JULIA_TOOL:-/scratch/rrlvandergeest/find2fix-herb/find2fix.jl}
JULIA_PROJECT=${JULIA_PROJECT:-/scratch/rrlvandergeest/find2fix-herb}
RESULTS_BASE=${RESULTS_BASE:-$ASTOR_ROOT}
JOBS_DIR=${JOBS_DIR:-$SCRIPT_DIR/jobs}
MAXTIME=${MAXTIME:-60}
BUFFER=${BUFFER:-20}
JAVA_LEVEL=${JAVA_LEVEL:-8}
STOPFIRST=${STOPFIRST:-true}
PARTITION=${PARTITION:-compute}
ACCOUNT=${ACCOUNT:-education-eemcs-msc-cs}
CPUS=${CPUS:-6}
MEM_PER_CPU=${MEM_PER_CPU:-2G}

RUN_ONE="$ASTOR_ROOT/runD4JBug.sh"
DEFECTS4J="$D4J_BIN/defects4j"

# SLURM wall-time: explicit SLURM_TIME wins, else MAXTIME+BUFFER as HH:MM:SS.
if [ -z "${SLURM_TIME:-}" ]; then
    total_min=$(( MAXTIME + BUFFER ))
    SLURM_TIME=$(printf '%02d:%02d:00' $(( total_min / 60 )) $(( total_min % 60 )))
fi

# Map a mode to the results-root directory name (matches runAllD4JCardumen.sh).
results_dir_for() {
    case "$1" in
        bfs)      echo "$RESULTS_BASE/d4j-cardumen-bfs-results" ;;
        mlfs)     echo "$RESULTS_BASE/d4j-cardumen-mlfs-results" ;;
        cardumen) echo "$RESULTS_BASE/d4j-cardumen-results" ;;
        *) echo "Error: unknown mode '$1'" >&2; return 1 ;;
    esac
}

# --- argument parsing --------------------------------------------------------
MODES="cardumen bfs mlfs"
while [ $# -gt 0 ]; do
    case "$1" in
        -m|--modes) [ $# -ge 2 ] || { echo "Error: $1 requires a value" >&2; exit 2; }
                    MODES=$2; shift 2 ;;
        --modes=*)  MODES=${1#*=}; shift ;;
        --)         shift; break ;;
        -*)         echo "Error: unknown option '$1'" >&2; exit 2 ;;
        *)          break ;;
    esac
done
for m in $MODES; do
    case "$m" in
        cardumen|bfs|mlfs) ;;
        *) echo "Error: mode must be 'cardumen', 'bfs' or 'mlfs', got '$m'" >&2; exit 2 ;;
    esac
done
PROJECTS=("$@")   # empty => all projects

# --- sanity checks -----------------------------------------------------------
[ -x "$DEFECTS4J" ] || { echo "Error: defects4j not found/executable at $DEFECTS4J" >&2; exit 1; }
[ -f "$RUN_ONE" ]   || { echo "Error: runD4JBug.sh not found at $RUN_ONE" >&2; exit 1; }

if [ "${#PROJECTS[@]}" -eq 0 ]; then
    mapfile -t PROJECTS < <("$DEFECTS4J" pids 2>/dev/null)
fi

# --- generate ----------------------------------------------------------------
mkdir -p "$JOBS_DIR"
SUBMIT_ALL="$JOBS_DIR/submit_all.sh"
{
    echo "#!/usr/bin/env bash"
    echo "# Auto-generated by generate_jobs.sh — sbatch every generated job."
    echo "# A bug/mode already marked .done is skipped (delete the marker or pass FORCE=1 to resubmit)."
    echo "set -euo pipefail"
    echo "cd \"\$(dirname \"\${BASH_SOURCE[0]}\")\""
} > "$SUBMIT_ALL"

job_count=0
for mode in $MODES; do
    results_root=$(results_dir_for "$mode")
    mode_dir="$JOBS_DIR/$mode"
    log_dir="$JOBS_DIR/logs/$mode"
    mkdir -p "$mode_dir" "$log_dir"

    for p in "${PROJECTS[@]}"; do
        while read -r b; do
            [ -n "$b" ] || continue
            id="${p}-${b}"
            job_file="$mode_dir/${id}.sbatch"
            bugdir="$results_root/$id"

            cat > "$job_file" <<EOF
#!/bin/bash
#SBATCH --partition=$PARTITION
#SBATCH --account=$ACCOUNT
#SBATCH --time=$SLURM_TIME
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=$CPUS
#SBATCH --mem-per-cpu=$MEM_PER_CPU
#SBATCH --job-name="${mode}-${id}"
#SBATCH --output=$log_dir/${id}-%j.out

module load 2025
module load subversion
module load julia

set -uo pipefail

# Repair this single Defects4J bug with one engine. Paths are baked in at
# generation time so the job is reproducible regardless of the submit cwd.
export D4J_BIN="$D4J_BIN"
export ASTOR_JAR="$ASTOR_JAR"
export JULIA_TOOL="$JULIA_TOOL"
export JULIA_PROJECT="$JULIA_PROJECT"
export JAVA_LEVEL="$JAVA_LEVEL"
export MAXTIME="$MAXTIME"
export STOPFIRST="$STOPFIRST"

bugdir="$bugdir"
mkdir -p "\$bugdir"

# Per-bug isolation: separate checkout root and Astor output dir, matching
# runAllD4JCardumen.sh so generate_results_table.py finds the same layout.
export OUT="\$bugdir/astor-output"
export WORK_ROOT="\$bugdir/checkout"

if srun bash "$RUN_ONE" "$p" "$b" "$mode" > "\$bugdir/run.log" 2>&1; then
    rm -f "\$bugdir/.error"
    touch "\$bugdir/.done"
else
    rc=\$?
    rm -f "\$bugdir/.done"
    echo "\$rc" > "\$bugdir/.error"
    exit "\$rc"
fi
EOF
            chmod +x "$job_file"

            # Add a guarded sbatch line to submit_all.sh.
            cat >> "$SUBMIT_ALL" <<EOF
if [ -n "\${FORCE:-}" ] || [ ! -f "$bugdir/.done" ]; then sbatch "$mode/${id}.sbatch"; fi
EOF
            job_count=$((job_count + 1))
        done < <("$DEFECTS4J" bids -p "$p" 2>/dev/null | grep -E '^[0-9]+$')
    done
done

chmod +x "$SUBMIT_ALL"

echo ">> generated $job_count job script(s) under $JOBS_DIR"
echo ">> modes: $MODES"
echo ">> projects: ${PROJECTS[*]}"
echo ">> wall-time per job: $SLURM_TIME (Astor maxtime ${MAXTIME}m + ${BUFFER}m buffer)"
echo ">> submit them all on the cluster with:  bash ${SUBMIT_ALL#$ASTOR_ROOT/}"
