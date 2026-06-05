#!/usr/bin/env bash
#
# Run Cardumen on a single Defects4J v2.0 bug.
#
# Usage:
#   ./runD4JBug.sh <Project> <Version> [engine]
#
#   <Project>   Defects4J project id   (e.g. Math, Lang, Chart, Time, ...)
#   <Version>   Defects4J bug number   (e.g. 70)        -> checks out <Version>b
#   [engine]    export   (default) CardumenExportEngine + Julia find2fix.jl tool
#               cardumen           plain Cardumen template-based repair (no Julia)
#
# Examples:
#   ./runD4JBug.sh Math 70
#   ./runD4JBug.sh Math 70 cardumen
#   WORK_ROOT=/tmp/d4j JAVA_LEVEL=7 ./runD4JBug.sh Lang 1
#
# Paths (override via environment):
#   defects4j path:  ~/thesis/defects4j-2.0/framework/bin
#   astor jar file:  ~/thesis/astor/target/astor-2.0.0-jar-with-dependencies.jar
#   julia tool path: ~/thesis/herb/find2fix.jl

set -euo pipefail

# --- configuration (env-overridable) ----------------------------------------
D4J_BIN=${D4J_BIN:-$HOME/thesis/defects4j-2.0/framework/bin}
ASTOR_JAR=${ASTOR_JAR:-$HOME/thesis/astor/target/astor-2.0.0-jar-with-dependencies.jar}
JULIA_TOOL=${JULIA_TOOL:-$HOME/thesis/herb/find2fix.jl}
JULIA_PROJECT=${JULIA_PROJECT:-$HOME/thesis/herb}
WORK_ROOT=${WORK_ROOT:-./tempdj4}   # root under which per-bug working dirs live
OUT=${OUT:-}                        # astor output root (-out); empty = astor default
JAVA_LEVEL=${JAVA_LEVEL:-8}         # -javacompliancelevel
MAXTIME=${MAXTIME:-60}              # -maxtime, in minutes
STOPFIRST=${STOPFIRST:-true}        # -stopfirst: stop this bug once the 1st patch is found (set false to keep searching)

# --- argument parsing --------------------------------------------------------
usage() {
    echo "Usage: $0 <Project> <Version> [export|cardumen]" >&2
    echo "  e.g. $0 Math 70            (CardumenExportEngine + Julia, default)" >&2
    echo "       $0 Math 70 cardumen   (plain Cardumen)" >&2
    exit 2
}

[ $# -ge 2 ] || usage
PROJECT=$1
VERSION=$2
ENGINE=${3:-${ENGINE:-export}}

case "$ENGINE" in
    export|cardumen) ;;
    *) echo "Error: engine must be 'export' or 'cardumen', got '$ENGINE'" >&2; usage ;;
esac

# --- sanity checks -----------------------------------------------------------
DEFECTS4J="$D4J_BIN/defects4j"
[ -x "$DEFECTS4J" ] || { echo "Error: defects4j not found/executable at $DEFECTS4J" >&2; exit 1; }
[ -f "$ASTOR_JAR" ] || { echo "Error: astor jar not found at $ASTOR_JAR" >&2; \
    echo "       build it with: mvn package -DskipTests=true" >&2; exit 1; }
if [ "$ENGINE" = "export" ] && [ ! -f "$JULIA_TOOL" ]; then
    echo "Warning: julia tool not found at $JULIA_TOOL; engine will fall back to constant '0'" >&2
fi
export PATH="$D4J_BIN:$PATH"

BUG_ID="${PROJECT}-${VERSION}"
WORKDIR="${WORK_ROOT}/${BUG_ID}"

# --- checkout (reuse if already present) -------------------------------------
if [ -d "$WORKDIR" ]; then
    echo ">> Reusing existing working directory: $WORKDIR (resetting to pristine state)"
    git -C "$WORKDIR" reset --hard --quiet   # discard any source modifications
    git -C "$WORKDIR" clean -fdq             # remove untracked files (incl. exported .txt)
else
    echo ">> Checking out ${PROJECT} ${VERSION}b into $WORKDIR"
    mkdir -p "$WORK_ROOT"   # defects4j won't create intermediate parent dirs
    "$DEFECTS4J" checkout -p "$PROJECT" -v "${VERSION}b" -w "$WORKDIR"
fi

# --- compile -----------------------------------------------------------------
echo ">> Compiling"
"$DEFECTS4J" compile -w "$WORKDIR"

# --- export project metadata -------------------------------------------------
# defects4j export prints the value to stdout (progress goes to stderr).
d4j_export() { "$DEFECTS4J" export -p "$1" -w "$WORKDIR" 2>/dev/null; }

SRC_DIR=$(d4j_export dir.src.classes)
TEST_DIR=$(d4j_export dir.src.tests)
BIN_DIR=$(d4j_export dir.bin.classes)
BIN_TEST_DIR=$(d4j_export dir.bin.tests)
CP_TEST=$(d4j_export cp.test)     # already includes the compile classpath
TRIGGERS=$(d4j_export tests.trigger)

# Failing test classes for fault localization: strip "::method", dedupe, join ':'
FAILING=$(printf '%s\n' "$TRIGGERS" | sed 's/::.*//' | sort -u | paste -sd:)
[ -n "$FAILING" ] || { echo "Error: no trigger tests found for $BUG_ID" >&2; exit 1; }

LOCATION=$(cd "$WORKDIR" && pwd)

echo ">> src=$SRC_DIR test=$TEST_DIR bin=$BIN_DIR bintest=$BIN_TEST_DIR"
echo ">> failing=$FAILING"
echo ">> engine=$ENGINE"

# --- engine-specific arguments -----------------------------------------------
JVM_PROPS=()
MODE_ARGS=()
if [ "$ENGINE" = "export" ]; then
    JVM_PROPS=( -Dcardumen.julia.tool="$JULIA_TOOL" -Dcardumen.julia.project="$JULIA_PROJECT" )
    MODE_ARGS=( -mode custom -customengine fr.inria.astor.approaches.cardumen.CardumenExportEngine )
else
    MODE_ARGS=( -mode cardumen )
fi

# Resolve the output directory (always explicit). Astor writes results to
# <OUTDIR>/AstorMain-<id>. We also run the JVM with this as its working
# directory so the GZoltar/JaCoCo coverage file (test-runner.exec) is written
# here, beside the bug's output, instead of polluting the launch directory.
# Per-bug OUTDIR also keeps parallel runs from clobbering each other's .exec.
if [ -n "$OUT" ]; then
    mkdir -p "$OUT"; OUTDIR=$(cd "$OUT" && pwd)
else
    OUTDIR="$(pwd)/output_astor"; mkdir -p "$OUTDIR"   # astor's default location
fi
ASTOR_JAR=$(cd "$(dirname "$ASTOR_JAR")" && pwd)/$(basename "$ASTOR_JAR")  # absolutize for cwd change

# --- run astor ---------------------------------------------------------------
echo ">> Running Astor (cwd=$OUTDIR)"
( cd "$OUTDIR" && exec java "${JVM_PROPS[@]}" -cp "$ASTOR_JAR" fr.inria.main.evolution.AstorMain \
    "${MODE_ARGS[@]}" \
    -out "$OUTDIR" \
    -id "$BUG_ID" \
    -location "$LOCATION" \
    -srcjavafolder "/$SRC_DIR" \
    -srctestfolder "/$TEST_DIR" \
    -binjavafolder "/$BIN_DIR" \
    -bintestfolder "/$BIN_TEST_DIR" \
    -dependencies "$CP_TEST" \
    -failing "$FAILING" \
    -javacompliancelevel "$JAVA_LEVEL" \
    -population 1 \
    -seed 0 \
    -scope local \
    -flthreshold 0.1 \
    -maxgen 1000000 \
    -maxtime "$MAXTIME" \
    -stopfirst "$STOPFIRST" \
    -parameters keepcomments:false \
    -loglevel INFO )
