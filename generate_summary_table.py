#!/usr/bin/env python3
"""
Generate a LaTeX summary table comparing Cardumen, BFS and MLFS.

Usage:
    python generate_summary_table.py [output.tex] [--whitelist single-line-bugs.txt]

Only single-line bugs (those listed in the whitelist) that were run to completion
by *all three* approaches are counted, so the numbers are directly comparable.
For each approach the table reports how many of those bugs it fixed, how many it
fixed exclusively, and -- as a matrix -- how many bugs it missed that each of the
other approaches fixed.

Required LaTeX packages (add to preamble):
    \\usepackage{booktabs}   % toprule/midrule/bottomrule/cmidrule
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_results_table import copy_to_clipboard, load_whitelist, patch_found

APPROACHES = ["Cardumen", "BFS", "MLFS"]

BUG_DIR_RE = re.compile(r"^([A-Za-z][A-Za-z0-9]*)-(\d+)$")


def find_common_bugs(dirs, whitelist):
    """Return ``{approach: {(project, id), ...}}`` of fixes over commonly run bugs.

    ``dirs`` maps an approach name to its results directory. Only bugs in
    ``whitelist`` are considered, and a bug is included only when every approach
    has a completion marker for it (``patch_found`` is not ``None``), i.e. all
    three actually ran it; the returned tuple also gives that common bug set so
    callers can report on it.
    """
    candidates = set()
    for base in dirs.values():
        base_path = Path(base)
        if not base_path.is_dir():
            print(f"Error: directory not found: {base}", file=sys.stderr)
            sys.exit(1)
        for entry in base_path.iterdir():
            m = BUG_DIR_RE.match(entry.name)
            if entry.is_dir() and m:
                candidates.add((m.group(1), int(m.group(2))))
    candidates &= whitelist

    common = set()
    fixed = {name: set() for name in dirs}
    for project, bug_id in candidates:
        results = {
            name: patch_found(base, project, bug_id) for name, base in dirs.items()
        }
        if any(r is None for r in results.values()):
            continue
        common.add((project, bug_id))
        for name, result in results.items():
            if result:
                fixed[name].add((project, bug_id))

    return common, fixed


def build_rows(fixed):
    """Return one dict of counts per approach."""
    rows = []
    for name in APPROACHES:
        mine = fixed[name]
        others = {o: fixed[o] for o in APPROACHES if o != name}
        union_others = set().union(*others.values()) if others else set()
        row = {
            "approach": name,
            "fixed": len(mine),
            "only": len(mine - union_others),
            "missed_by_other": {o: len(theirs - mine) for o, theirs in others.items()},
            "missed_any": len(union_others - mine),
        }
        rows.append(row)
    return rows


def generate_table(common, fixed, whitelist_name):
    rows = build_rows(fixed)

    # approach + fixed + only, then one matrix column per approach (the
    # diagonal is a dash) plus the "any other approach" column
    n_lead = 2
    n_matrix = len(APPROACHES) + 1
    n_cols = 1 + n_lead + n_matrix
    matrix_first = 2 + n_lead

    lines = []
    lines.append(r"\begin{table}[ht]")
    lines.append(r"  \centering")
    lines.append(r"  \begin{tabular}{" + "l" + "r" * (n_cols - 1) + r"}")
    lines.append(r"    \toprule")
    lines.append(
        "    "
        + " & " * (1 + n_lead)
        + r"\multicolumn{"
        + str(n_matrix)
        + r"}{c}{\textbf{Missed, but fixed by}} \\"
    )
    lines.append(r"    \cmidrule(l){" + f"{matrix_first}-{n_cols}" + r"}")

    header = [r"\textbf{Approach}", r"\textbf{Fixed}", r"\textbf{Only}"]
    header += [rf"\textbf{{{o}}}" for o in APPROACHES]
    header.append(r"\textbf{Any}")
    lines.append("    " + " & ".join(header) + r" \\")
    lines.append(r"    \midrule")

    for row in rows:
        cells = [row["approach"], str(row["fixed"]), str(row["only"])]
        for other in APPROACHES:
            if other == row["approach"]:
                cells.append(r"---")
            else:
                cells.append(str(row["missed_by_other"][other]))
        cells.append(str(row["missed_any"]))
        lines.append("    " + " & ".join(cells) + r" \\")

    lines.append(r"    \bottomrule")
    lines.append(r"  \end{tabular}")

    caption = (
        r"  \caption{Repair results over the "
        + str(len(common))
        + r" single-line Defects4J bugs"
        + r" that were run by all three approaches."
        r" \emph{Fixed} counts the bugs for which the approach produced a"
        r" plausible patch"
    )
    caption += (
        r", and \emph{Only} counts the bugs that no other approach fixed."
        r" The \emph{Missed, but fixed by} columns give, per row, the number of"
        r" bugs that approach failed to fix while the column's approach fixed"
        r" them; \emph{Any} is the number missed but fixed by at least one other"
        r" approach.}"
    )
    lines.append(caption)
    lines.append(r"  \label{tab:approach-summary}")
    lines.append(r"\end{table}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Generate a LaTeX summary table comparing Cardumen, BFS and MLFS."
    )
    parser.add_argument("output", nargs="?", help="Output .tex file (default: stdout)")
    parser.add_argument("--copy", action="store_true", help="Copy the table to the clipboard")
    parser.add_argument(
        "--cardumen-dir",
        default="d4j-cardumen-results",
        help="Path to the Cardumen results directory (default: d4j-cardumen-results)",
    )
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
        default="single-line-bugs.txt",
        help="Path to the single-line bug whitelist (default: single-line-bugs.txt); "
             "only these bugs are counted",
    )
    args = parser.parse_args()

    dirs = {
        "Cardumen": args.cardumen_dir,
        "BFS": args.bfs_dir,
        "MLFS": args.mlfs_dir,
    }

    whitelist = load_whitelist(args.whitelist)
    common, fixed = find_common_bugs(dirs, whitelist)
    if not common:
        print(
            "Warning: no whitelisted bug was run by all three approaches.",
            file=sys.stderr,
        )

    table = generate_table(common, fixed, Path(args.whitelist).name)

    if args.output:
        Path(args.output).write_text(table + "\n")
        print(f"Written to {args.output}")
    else:
        print(table)

    if args.copy:
        cmd = copy_to_clipboard(table)
        if cmd:
            print(f"Copied to clipboard via {cmd}.", file=sys.stderr)


if __name__ == "__main__":
    main()