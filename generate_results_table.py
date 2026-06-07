#!/usr/bin/env python3
"""
Generate a LaTeX table from d4j-cardumen-results.

Usage:
    python generate_results_table.py <results-dir> [output.tex]

For each <Project>-<ID> directory found in <results-dir>, emits a table row
with the project name, bug id, whether a diffSolutions folder was found
(Cardumen), whether the matching ExportEngine run found a patch (BFS, read
from --bfs-dir), and one empty column (MLFS) for manual completion.

Required LaTeX packages (add to preamble):
    \\usepackage{booktabs}   % toprule/midrule/bottomrule/cmidrule
    \\usepackage{multirow}   % multirow project cells
    \\usepackage{bbding}     % Checkmark, XSolidBrush
"""

import argparse
import json
import re
import subprocess
import sys
from itertools import groupby
from pathlib import Path


def bfs_patch_found(bfs_dir, project, bug_id):
    """Return True if the ExportEngine run for this bug found a patch.

    The export engine writes an ``astor_output.json`` whose
    ``general.OUTPUT_STATUS`` is ``STOP_BY_PATCH_FOUND`` when a plausible
    patch was synthesised. The patch list itself is not serialised, so the
    status field is the reliable signal.
    """
    if bfs_dir is None:
        return False
    name = f"{project}-{bug_id}"
    json_path = (
        Path(bfs_dir) / name / "astor-output" / f"AstorMain-{name}" / "astor_output.json"
    )
    if not json_path.is_file():
        return False
    try:
        data = json.loads(json_path.read_text())
    except (ValueError, OSError):
        return False
    return data.get("general", {}).get("OUTPUT_STATUS") == "STOP_BY_PATCH_FOUND"


def find_bugs(results_dir, bfs_dir=None):
    pattern = re.compile(r'^([A-Za-z][A-Za-z0-9]*)-(\d+)$')
    results_path = Path(results_dir)
    if not results_path.is_dir():
        print(f"Error: directory not found: {results_dir}", file=sys.stderr)
        sys.exit(1)

    bugs = []
    for entry in results_path.iterdir():
        if not entry.is_dir():
            continue
        m = pattern.match(entry.name)
        if not m:
            continue
        project = m.group(1)
        bug_id = int(m.group(2))
        has_patch = (entry / "astor-output" / "diffSolutions").is_dir()
        has_bfs = bfs_patch_found(bfs_dir, project, bug_id)
        bugs.append((project, bug_id, has_patch, has_bfs))

    bugs.sort(key=lambda x: (x[0], x[1]))
    return bugs


def group_bugs(bugs):
    """Return list of (project, [(project, bug_id, has_patch), ...]) pairs."""
    return [(proj, list(items)) for proj, items in groupby(bugs, key=lambda x: x[0])]


def split_groups(groups, n=3):
    """Split groups into n parts at project boundaries closest to equal thirds."""
    n = min(n, len(groups))
    total = sum(len(items) for _, items in groups)
    targets = [total * k / n for k in range(1, n)]
    split_indices = []

    cumulative = 0
    t_idx = 0
    best_idx = 1
    best_dist = float("inf")

    for i, (_, items) in enumerate(groups):
        cumulative += len(items)
        if t_idx >= len(targets):
            break
        dist = abs(cumulative - targets[t_idx])
        if dist < best_dist and 0 < i < len(groups) - 1:
            best_dist = dist
            best_idx = i + 1
        if i < len(groups) - 2 and abs(cumulative - targets[t_idx]) > abs(
            cumulative + len(groups[i + 1][1]) - targets[t_idx]
        ):
            continue
        if i >= len(groups) - 2 or cumulative >= targets[t_idx]:
            split_indices.append(best_idx)
            t_idx += 1
            best_dist = float("inf")

    parts = []
    prev = 0
    for idx in split_indices:
        parts.append(groups[prev:idx])
        prev = idx
    parts.append(groups[prev:])
    return parts


def build_tabular(groups):
    lines = []
    max_len = max((len(proj) for proj, _ in groups), default=5)
    col_width = f"{max(3.0, max_len * 0.6):.1f}em"
    lines.append(r"    {\scriptsize")
    lines.append(r"    \begin{tabular}{p{" + col_width + r"} r c c c}")
    lines.append(r"      \toprule")
    lines.append(
        r"      \textbf{Project} & \textbf{ID} & \textbf{Cardumen} & \textbf{BFS} & \textbf{MLFS} \\"
    )
    lines.append(r"      \midrule")

    for g_idx, (project, items) in enumerate(groups):
        if g_idx > 0:
            lines.append(r"      \cmidrule{2-5}")
        count = len(items)
        proj_cell = r"\multirow{" + str(count) + r"}{*}{\centering " + project + r"}"
        for i, (_, bug_id, has_patch, has_bfs) in enumerate(items):
            mark = r"\Checkmark" if has_patch else r"\XSolidBrush"
            bfs_mark = r"\Checkmark" if has_bfs else r"\XSolidBrush"
            cell = proj_cell if i == 0 else ""
            lines.append(f"      {cell} & {bug_id} & {mark} & {bfs_mark} & \\\\")

    lines.append(r"      \bottomrule")
    lines.append(r"    \end{tabular}")
    lines.append(r"    }")
    return lines


def generate_table(bugs, patches_only=True):
    if patches_only:
        bugs = [b for b in bugs if b[2] or b[3]]
    groups = group_bugs(bugs)
    parts = split_groups(groups, n=2)

    lines = []
    lines.append(r"\begin{table}[ht]")
    lines.append(r"  \centering")

    for i, part in enumerate(parts):
        lines.append(r"  \begin{minipage}[t]{0.48\textwidth}")
        lines.append(r"    \centering")
        lines += build_tabular(part)
        if i < len(parts) - 1:
            lines.append(r"  \end{minipage}%")
            lines.append(r"  \hfill%")
        else:
            lines.append(r"  \end{minipage}")

    lines.append(
        r"  \caption{Cardumen repair results on Defects4J benchmarks."
        r" \emph{Cardumen} indicates whether Cardumen produced a plausible patch"
        r" \emph{BFS} and \emph{MLFS} indicate if a patch was found with program synthesis"
        r" using BFS and MLFS respectively.}"
    )
    lines.append(r"  \label{tab:cardumen-results}")
    lines.append(r"\end{table}")
    return "\n".join(lines)


def copy_via_osc52(text):
    import base64
    payload = base64.b64encode(text.encode()).decode()
    sequence = f"\033]52;c;{payload}\007"
    try:
        with open("/dev/tty", "w") as tty:
            tty.write(sequence)
            tty.flush()
    except OSError:
        sys.stderr.write(sequence)
        sys.stderr.flush()


def copy_to_clipboard(text):
    candidates = ["wl-copy", "clip.exe", "xclip -selection clipboard", "xsel --clipboard --input", "pbcopy"]
    for cmd in candidates:
        parts = cmd.split()
        try:
            subprocess.run(parts, input=text.encode(), check=True)
            return parts[0]
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
    copy_via_osc52(text)
    return "OSC 52"


def main():
    parser = argparse.ArgumentParser(
        description="Generate LaTeX results table from d4j-cardumen-results."
    )
    parser.add_argument("results_dir", help="Path to the results directory")
    parser.add_argument("output", nargs="?", help="Output .tex file (default: stdout)")
    parser.add_argument("--copy", action="store_true", help="Copy the table to the clipboard")
    parser.add_argument("--all", action="store_true", help="Include bugs without a patch (default: patches only)")
    parser.add_argument(
        "--bfs-dir",
        default="d4j-cardumen-export-results",
        help="Path to the ExportEngine (BFS) results directory (default: d4j-cardumen-export-results)",
    )
    args = parser.parse_args()

    bugs = find_bugs(args.results_dir, args.bfs_dir)
    if not bugs:
        print("Warning: no <Project>-<ID> directories found.", file=sys.stderr)

    table = generate_table(bugs, patches_only=not args.all)

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
