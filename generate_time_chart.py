#!/usr/bin/env python3
"""
Generate a LaTeX pgfplots chart of time-to-patch from d4j-cardumen-results.

Usage:
    python generate_time_chart.py <results-dir> [output.tex] [--plot {box,bar}] [--whitelist FILE]

For each <Project>-<ID> directory found in <results-dir> that produced a
plausible patch (astor-output/diffSolutions), reads the time (in seconds)
until that patch was found from astor_output.json. Bugs are grouped by
project, and for Cardumen (in <results-dir>), BFS (in --bfs-dir), and MLFS
(in --mlfs-dir) the distribution of time-to-patch across that project's
solved bugs is plotted per approach per project.

--plot box (default) draws a box plot: median, IQR box, 1.5x IQR whiskers,
and outliers as points, computed by pgfplots from the raw per-bug times.
--plot bar draws a bar chart of the median time-to-patch instead.
Either way, a project/approach combination with no solved bugs is omitted
(no box/bar), and a project with no solved bugs in any approach is left off
the chart entirely.

Required LaTeX packages (add to preamble):
    \\usepackage{pgfplots}
    \\pgfplotsset{compat=1.17}
    \\usepgfplotslibrary{statistics}   % only needed for --plot box
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
BOX_COLORS = ["blue!60", "red!60", "green!60!black"]
BOX_OFFSETS = [-0.24, 0, 0.24]


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


def times_by_project(entries):
    """Return [(project, [times_cardumen, times_bfs, times_mlfs]), ...].

    Each column is the (possibly empty) list of raw per-bug times for bugs in
    that project solved by that approach. Projects with no data in any
    approach are dropped.
    """
    grouped = []
    for project, items in groupby(entries, key=lambda x: x[0]):
        items = list(items)
        columns = []
        for col in range(2, 5):
            columns.append([item[col] for item in items if item[col] is not None])
        if any(columns):
            grouped.append((project, columns))
    return grouped


def _axis_preamble(projects, extra_options):
    lines = []
    lines.append(r"  \begin{tikzpicture}")
    lines.append(r"  \begin{axis}[")
    lines.append(r"      width=\textwidth,")
    lines.append(r"      height=0.45\textwidth,")
    lines.append(r"      ymode=log,")
    lines.append(r"      ymin=1,")
    lines.append(r"      ylabel={Time to patch (s)},")
    lines.append(r"      xlabel={Project},")
    lines.append(r"      xlabel style={at={(0.5,-0.25)}},")
    lines.extend(extra_options)
    lines.append(r"      x tick label style={rotate=45, anchor=east},")
    lines.append(r"      ymajorgrids,")
    lines.append(r"      major grid style={dotted,gray},")
    lines.append(r"      legend style={at={(0.5,-0.5)}, anchor=north, legend columns=-1},")
    lines.append(r"      legend cell align=left,")
    lines.append(r"  ]")
    return lines


def build_bar_chart(grouped, stat="median"):
    projects = [project for project, _ in grouped]
    agg = statistics.mean if stat == "mean" else statistics.median
    stat_label = "Mean" if stat == "mean" else "Median"

    lines = [r"\begin{figure}[ht]", r"  \centering"]
    lines += _axis_preamble(projects, [
        r"      ybar,",
        r"      bar width=6pt,",
        r"      symbolic x coords={" + ",".join(projects) + r"},",
        # List every project explicitly rather than xtick=data: with grouped
        # ybar, xtick=data only labels the first plot's coordinates, so a
        # project missing from the first approach (e.g. Cardumen has no Time)
        # would otherwise leave that group's bars unlabelled.
        r"      xtick={" + ",".join(projects) + r"},",
        r"      enlarge x limits=0.04,",
    ])

    for col in range(3):
        coords = " ".join(
            f"({project},{agg(values):g})"
            for project, columns in grouped
            if (values := columns[col])
        )
        lines.append(r"  \addplot+[fill] coordinates {")
        lines.append(f"      {coords}")
        lines.append(r"  };")

    lines.append(r"  \legend{" + ", ".join(APPROACHES) + r"}")
    lines.append(r"  \end{axis}")
    lines.append(r"  \end{tikzpicture}")
    lines.append(
        r"  \caption{" + stat_label + r" time to patch discovery per project, by"
        r" approach (log scale). Bars are omitted where an approach found no patch"
        r" for that project.}"
    )
    lines.append(r"  \label{fig:time-to-patch}")
    lines.append(r"\end{figure}")
    return "\n".join(lines)


def build_box_plot(grouped):
    projects = [project for project, _ in grouped]
    n = len(projects)

    lines = [r"\begin{figure}[ht]", r"  \centering"]
    lines += _axis_preamble(projects, [
        r"      boxplot/draw direction=y,",
        r"      boxplot/box extend=0.2,",
        r"      xtick={" + ",".join(str(i + 1) for i in range(n)) + r"},",
        r"      xticklabels={" + ",".join(projects) + r"},",
        r"      xtick style={draw=none},",
        r"      xmin=0.5,",
        f"      xmax={n + 0.5},",
    ])

    has_data = [False, False, False]
    for i, (project, columns) in enumerate(grouped, start=1):
        for col in range(3):
            values = columns[col]
            if not values:
                continue
            has_data[col] = True
            position = i + BOX_OFFSETS[col]
            options = f"boxplot, fill={BOX_COLORS[col]}, draw=black, forget plot"
            lines.append(
                r"  \addplot+[" + options + r", boxplot/draw position="
                + f"{position:g}" + r"] table[y index=0] {"
            )
            lines.append(r"      y")
            for v in values:
                lines.append(f"      {v:g}")
            lines.append(r"  };")

    # Boxplot's own legend glyph is a mini box-and-whisker icon; add plain
    # color-swatch legend entries instead, decoupled from the actual plots.
    for col in range(3):
        if not has_data[col]:
            continue
        lines.append(
            r"  \addlegendimage{area legend, fill=" + BOX_COLORS[col] + r", draw=black}"
        )
        lines.append(r"  \addlegendentry{" + APPROACHES[col] + r"}")

    lines.append(r"  \end{axis}")
    lines.append(r"  \end{tikzpicture}")
    lines.append(
        r"  \caption{Time to patch discovery per project, by approach"
        r" (log scale). Boxes show the interquartile range and median;"
        r" whiskers extend to $1.5\times$ IQR, with individual points beyond"
        r" that shown as outliers. A box is omitted where an approach found"
        r" no patch for that project.}"
    )
    lines.append(r"  \label{fig:time-to-patch}")
    lines.append(r"\end{figure}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Generate a LaTeX pgfplots chart of time-to-patch from d4j-cardumen-results."
    )
    parser.add_argument(
        "results_dir",
        nargs="?",
        default="d4j-cardumen-results",
        help="Path to the results directory (default: d4j-cardumen-results)",
    )
    parser.add_argument("output", nargs="?", help="Output .tex file (default: stdout)")
    parser.add_argument(
        "--plot",
        choices=["box", "bar"],
        default="box",
        help="Chart type: box plot of the full distribution, or bar chart of "
             "an aggregate (default: box)",
    )
    parser.add_argument(
        "--stat",
        choices=["median", "mean"],
        default="median",
        help="For --plot bar, the aggregate to plot per project/approach "
             "(default: median)",
    )
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

    grouped = times_by_project(entries)
    if not grouped:
        print("Warning: no bugs with a found patch; chart will be empty.", file=sys.stderr)

    chart = build_box_plot(grouped) if args.plot == "box" else build_bar_chart(grouped, args.stat)

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
