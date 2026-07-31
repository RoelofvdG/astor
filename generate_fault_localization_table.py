#!/usr/bin/env python3
"""Generate a LaTeX booktabs table: for every single-line bug, was the developer
patch location reachable by Astor?

Two verdicts per bug, both derived from Astor's own fault-localization output and
identical across the Cardumen / BFS / MLFS runs (they share the same spectrum
fault localization, so the *location* chance is common to all three -- they
differ only in whether they can synthesise the right ingredient there):

  * \\textbf{Localized} -- the developer-patched line is in the raw suspicious
    list produced by the fault localizer (run.log ``Suspicious:`` lines).
  * \\textbf{In search space} -- that line was turned into a modification point
    (suspicious_<bug>.json), i.e. a location Astor actually mutated. This is the
    real upper bound on a *correct* patch: if the line is not here, no ingredient
    search can place a fix at the developer's location.

A ``--`` in both columns means the run errored before fault localization
completed, so no verdict is possible.

Required LaTeX packages (add to preamble):
    \\usepackage{booktabs}
    \\usepackage{multirow}
    \\usepackage{bbding}     % \\Checkmark, \\XSolidBrush

Usage:
    python generate_fault_localization_table.py [output.tex] [--copy]
"""

import argparse
from pathlib import Path

from analyze_fault_localization import analyse
from generate_results_table import copy_to_clipboard


def counts(rows):
    c = {
        "in_space": sum(1 for r in rows if r["mp_hit"]),
        "loc_only": sum(1 for r in rows if r["fl_hit"] and not r["mp_hit"]),
        "not_loc": sum(1 for r in rows if r["fl_any"] and not r["fl_hit"]),
        "errored": sum(1 for r in rows if not r["fl_any"]),
    }
    c["total"] = len(rows)
    return c


def per_project(rows):
    """Ordered list of (project, counts) using the input row order."""
    order = []
    buckets = {}
    for r in rows:
        p = r["project"]
        if p not in buckets:
            buckets[p] = []
            order.append(p)
        buckets[p].append(r)
    return [(p, counts(buckets[p])) for p in order]


def data_row(label, c, bold=False):
    cells = [label, c["in_space"], c["loc_only"], c["not_loc"], c["errored"], c["total"]]
    if bold:
        cells = [cells[0]] + [r"\textbf{" + str(x) + r"}" for x in cells[1:]]
        cells[0] = r"\textbf{" + cells[0] + r"}"
    return "    " + " & ".join(str(x) for x in cells) + r" \\"


def generate_table(rows):
    lines = [
        r"\begin{table}[ht]",
        r"  \centering",
        r"  \begin{tabular}{l r r r r r}",
        r"    \toprule",
        r"    \textbf{Project} & \textbf{In space} & \textbf{Loc.\ only} & "
        r"\textbf{Not loc.} & \textbf{Errored} & \textbf{Total} \\",
        r"    \midrule",
    ]
    for project, c in per_project(rows):
        lines.append(data_row(project, c))
    lines.append(r"    \midrule")
    lines.append(data_row("Total", counts(rows), bold=True))
    lines += [
        r"    \bottomrule",
        r"  \end{tabular}",
        r"  \caption{"
        r"Reachability of the developer patch location per project, across the " + str(len(rows)) + r" single-line Defects4J bugs. \emph{In space}: the developer-patched line became a modification point in Astor. \emph{Loc.\ only}: the fault localizer flagged the line but Astor never made it into a modification point. \emph{Not loc.}: the line was not found by FL. \emph{Errored}: the run failed before FL completed. \emph{Total}: the total amount of single-line bugs in that project. The same FL is shared by the Cardumen, BFS and MLFS approaches, so they impact every approach's chance of a correct patch equally.",
        r"}",
        r"  \label{tab:fault-localization}",
        r"\end{table}",
    ]
    return "\n".join(lines)


def summary(rows):
    hit = sum(r["mp_hit"] for r in rows)
    fl_only = sum(1 for r in rows if r["fl_hit"] and not r["mp_hit"])
    fl_miss = sum(1 for r in rows if r["fl_any"] and not r["fl_hit"])
    crashed = sum(1 for r in rows if not r["fl_any"])
    return (
        f"% {len(rows)} single-line bugs: "
        f"{hit} in search space, "
        f"{fl_only} localized-but-not-modifiable, "
        f"{fl_miss} not localized, "
        f"{crashed} run errored (no verdict)."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", nargs="?", help="Output .tex file (default: stdout)")
    parser.add_argument("--copy", action="store_true", help="Copy the table to the clipboard")
    args = parser.parse_args()

    rows = analyse()
    table = summary(rows) + "\n" + generate_table(rows)

    if args.output:
        Path(args.output).write_text(table + "\n")
        print(f"Written to {args.output}")
    else:
        print(table)
    if args.copy:
        copy_to_clipboard(table)


if __name__ == "__main__":
    main()
