"""
Generate a LaTeX pgfplots bar chart of time-to-patch from d4j-cardumen-results.

Usage:
    python generate_time_chart.py <results-dir> [output.tex] [--whitelist FILE]

For each <Project>-<ID> directory found in <results-dir> that produced a
plausible patch (astor-output/diffSolutions), reads the time (in seconds)
until that patch was found from astor_output.json. Bugs are grouped by
project, and for Cardumen (in <results-dir>), BFS (in --bfs-dir), and MLFS
(in --mlfs-dir) the median time-to-patch across that project's solved bugs is
plotted as one bar per approach per project. A project/approach combination
with no solved bugs has no bar (rather than a zero-height bar), and a project
with no solved bugs in any approach is left off the chart entirely.

Required LaTeX packages (add to preamble):
    \\usepackage{pgfplots}
    \\pgfplotsset{compat=1.17}
"""

import argparse
import json
import re
import statistics
import sys
from itertools import groupby
from pathlib import Path

from generate_results_table import copy_to_clipboard, load_whitelist, patch_found

BUG_DIR_RE = re.compile(r'^([A-Za-z][A-Za-z0-9]*)-(\d+)$')

APPROACHES = ["Cardumen", "BFS", "MLFS"]


def bug_time(base_dir, project, bug_id):
    """Return the time in seconds until a patch was found, or None.

    None covers both "did not find a patch" and "base_dir not given" (see
    patch_found), so callers don't need to special-case a missing approach.
    """
    if patch_found(base_dir, project, bug_id) is not True:
        return None
    run_dir = Path(base_dir) / f"{project}-{bug_id}"
    output_json = run_dir / "astor-output" / f"AstorMain-{project}-{bug_id}" / "astor_output.json"
    try:
        data = json.loads(output_json.read_text())
        return float(data["patches"][0]["TIME"])
    except (OSError, ValueError, KeyError, IndexError) as e:
        print(f"Warning: {project}-{bug_id} has diffSolutions but no usable "
              f"time in {output_json}: {e}", file=sys.stderr)
        return None


def collect_bug_times(results_dir, bfs_dir=None, mlfs_dir=None, whitelist=None):
    results_path = Path(results_dir)
    if not results_path.is_dir():
        print(f"Error: directory not found: {results_dir}", file=sys.stderr)
        sys.exit(1)

    entries = []
    for entry in results_path.iterdir():
        if not entry.is_dir():
            continue
        m = BUG_DIR_RE.match(entry.name)
        if not m:
            continue
        project = m.group(1)
        bug_id = int(m.group(2))
        if whitelist is not None and (project, bug_id) not in whitelist:
            continue
        t_cardumen = bug_time(results_dir, project, bug_id)
        t_bfs = bug_time(bfs_dir, project, bug_id) if bfs_dir else None
        t_mlfs = bug_time(mlfs_dir, project, bug_id) if mlfs_dir else None
        entries.append((project, bug_id, t_cardumen, t_bfs, t_mlfs))

    entries.sort(key=lambda x: (x[0], x[1]))
    return entries


def median_by_project(entries):
    """Return [(project, [med_cardumen, med_bfs, med_mlfs]), ...].

    A column is None when no bug in that project found a patch with that
    approach. Projects with no data in any approach are dropped."""
    medians = []
    for project, items in groupby(entries, key=lambda x: x[0]):
        items = list(items)
        columns = []
        for col in range(2, 5):
            times = [item[col] for item in items if item[col] is not None]
            columns.append(statistics.median(times) if times else None)
        if any(c is not None for c in columns):
            medians.append((project, columns))
    return medians


def build_pgfplot(medians):
    projects = [project for project, _ in medians]

    lines = []
    lines.append(r"\begin{figure}[ht]")
    lines.append(r"  \centering")
    lines.append(r"  \begin{tikzpicture}")
    lines.append(r"  \begin{axis}[")
    lines.append(r"      ybar,")
    lines.append(r"      bar width=6pt,")
    lines.append(r"      width=\textwidth,")
    lines.append(r"      height=0.45\textwidth,")
    lines.append(r"      ymode=log,")
    lines.append(r"      ymin=1,")
    lines.append(r"      ylabel={Time to patch (s)},")
    lines.append(r"      xlabel={Project},")
    lines.append(r"      xlabel style={at={(0.5,-0.25)}},")
    lines.append(r"      symbolic x coords={" + ",".join(projects) + r"},")
    lines.append(r"      xtick=data,")
    lines.append(r"      x tick label style={rotate=45, anchor=east},")
    lines.append(r"      enlarge x limits=0.04,")
    lines.append(r"      ymajorgrids,")
    lines.append(r"      major grid style={dotted,gray},")
    lines.append(r"      legend style={at={(0.5,-0.5)}, anchor=north, legend columns=-1},")
    lines.append(r"      legend cell align=left,")
    lines.append(r"  ]")

    for col in range(3):
        coords = " ".join(
            f"({project},{value:g})"
            for project, columns in medians
            if (value := columns[col]) is not None
        )
        lines.append(r"  \addplot+[fill] coordinates {")
        lines.append(f"      {coords}")
        lines.append(r"  };")

    lines.append(r"  \legend{" + ", ".join(APPROACHES) + r"}")
    lines.append(r"  \end{axis}")
    lines.append(r"  \end{tikzpicture}")
    lines.append(
        r"  \caption{Median time to patch discovery per project, by approach"
        r" (log scale). Bars are omitted where an approach found no patch for"
        r" that project.}"
    )
    lines.append(r"  \label{fig:time-to-patch}")
    lines.append(r"\end{figure}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Generate a LaTeX pgfplots bar chart of time-to-patch from d4j-cardumen-results."
    )
    parser.add_argument(
        "results_dir",
        nargs="?",
        default="d4j-cardumen-results",
        help="Path to the results directory (default: d4j-cardumen-results)",
    )
    parser.add_argument("output", nargs="?", help="Output .tex file (default: stdout)")
    parser.add_argument("--copy", action="store_true", help="Copy the chart to the clipboard")
    parser.add_argument(
        "--bfs-dir",
        default="d4j-cardumen-bfs-results",
        help="Path to the BFS results directory (default: d4j-cardumen-bfs-results)",
    )
    parser.add_argument(
        "--mlfs-dir",
        default="d4j-cardumen-mlfs-results",
        help="Path to the MLFS results directory (default: d4j-cardumen-mlfs-results)",
    )
    parser.add_argument(
        "--whitelist",
        help="Path to a whitelist file (one '<Project> <ID>' per line); "
             "only listed bugs are included",
    )
    args = parser.parse_args()

    whitelist = load_whitelist(args.whitelist) if args.whitelist else None
    entries = collect_bug_times(args.results_dir, args.bfs_dir, args.mlfs_dir, whitelist)
    if not entries:
        print("Warning: no <Project>-<ID> directories found.", file=sys.stderr)

    medians = median_by_project(entries)
    if not medians:
        print("Warning: no bugs with a found patch; chart will be empty.", file=sys.stderr)

    chart = build_pgfplot(medians)

    if args.output:
        Path(args.output).write_text(chart + "\n")
        print(f"Written to {args.output}")
    else:
        print(chart)

    if args.copy:
        cmd = copy_to_clipboard(chart)
        if cmd:
            print(f"Copied to clipboard via {cmd}.", file=sys.stderr)


if __name__ == "__main__":
    main()