#!/usr/bin/env python3
"""
Generate a LaTeX appendix of patch diffs from d4j-cardumen-results.

Usage:
    python generate_diff_appendix.py <results-dir> [output.tex] [options]

Selects bugs by which approaches did or did not find a plausible patch, using
repeatable -y/--found and -n/--not-found flags naming an approach (cardumen,
bfs, mlfs). For example:

    -y mlfs -n cardumen              bugs where MLFS found a patch and Cardumen did not
    -y mlfs -n cardumen -n bfs       bugs where only MLFS found a patch
    (no -y/-n given)                 every bug with a patch from any approach

For each selected bug, emits a diff listing for every approach that found a
plausible patch, preceded by a one-line summary of which approaches did
(\\Checkmark), did not (\\XSolidBrush), or were not run (--) for that bug.
Bugs with no patch from any approach are skipped unless --all is given.

The diff shown is reconstructed from the structured patchhunks in
astor-output/diffSolutions/patchinfo_*.json (LOCATION/LINE/ORIGINAL_CODE/
PATCH_HUNK_CODE) rather than taken from Astor's own diffSolutions/*.diff
files: those are computed by a naive line-based diff over Astor's
pretty-printed output, which can balloon to hundreds of lines of unrelated
deletions when the pretty-printer garbles formatting after a single-token
edit, even though the actual change is one expression.

To keep lines within the page width, the file header uses the bare class
name (not the full package path) and fully-qualified type names in the code
(e.g. "org.jfree.chart.axis.CategoryLabelPositions") are shortened to their
simple name ("CategoryLabelPositions") -- this is Spoon's own printing
convention, not code a developer would write, so trimming it is a
readability win as well. Each listing also sets breaklines/breakatwhitespace
itself so the remaining long expressions still wrap instead of overflowing,
independent of the preamble's \\lstset. Along the way, stray double-escaped
characters left over from Astor's own JSON output (a literal "\\n", "\\/",
"\\"" or "\\\\") are also undone.

Required LaTeX packages (add to preamble):
    \\usepackage{listings}
    \\usepackage{xcolor}
    \\usepackage{bbding}   % Checkmark, XSolidBrush

    \\lstdefinelanguage{diff}{
      morecomment=[f][\\color{diffadd}]{+},
      morecomment=[f][\\color{diffdel}]{-},
    }
    \\colorlet{diffadd}{green!50!black}
    \\colorlet{diffdel}{red}
    \\lstset{
      language=diff,
      basicstyle=\\ttfamily\\scriptsize,
      frame=single,
    }
"""

import argparse
import json
import re
import sys
from pathlib import Path

from generate_results_table import copy_to_clipboard, load_whitelist, patch_found

BUG_DIR_RE = re.compile(r'^([A-Za-z][A-Za-z0-9]*)-(\d+)$')
APPROACHES = ["cardumen", "bfs", "mlfs"]
APPROACH_LABELS = {"cardumen": "Cardumen", "bfs": "BFS", "mlfs": "MLFS"}

# Matches a fully-qualified type name (e.g. "org.jfree.chart.axis.Foo" or
# "java.lang.Math" in "java.lang.Math.PI") so it can be shortened to its
# simple name; Spoon prints every type fully-qualified to avoid needing
# imports, which real diffs wouldn't do and which makes lines needlessly long.
FQN_RE = re.compile(r'\b(?:[a-z][a-zA-Z0-9]*\.)+([A-Z][A-Za-z0-9_]*)\b')

LSTLISTING_OPTS = "breaklines=true,breakatwhitespace=false"

# Astor double-escapes ORIGINAL_CODE/PATCH_HUNK_CODE (e.g. "Math.PI \/ 4.0",
# "\n" as a literal backslash-n instead of a real line break): these are JSON
# escapes that were never decoded. Undo them; a literal "\n" is a soft line
# wrap in Astor's pretty-printer, not a meaningful newline, so it becomes a
# space rather than an actual line break.
ESCAPE_RE = re.compile(r'\\(.)')
UNESCAPE_MAP = {'"': '"', '/': '/', '\\': '\\'}


def unescape_code(code):
    return ESCAPE_RE.sub(lambda m: ' ' if m.group(1) == 'n' else UNESCAPE_MAP.get(m.group(1), m.group(0)), code)


def simplify_fqn(code):
    return FQN_RE.sub(r'\1', code)


def approach_dir(args, approach):
    return {"cardumen": args.results_dir, "bfs": args.bfs_dir, "mlfs": args.mlfs_dir}[approach]


def read_hunks(base_dir, project, bug_id):
    """Return the patch hunks for a bug's plausible patch, or None.

    Each hunk is a ``(location, line, original_code, patch_hunk_code)``
    tuple read from diffSolutions/patchinfo_*.json. None covers both
    "approach not run" and "no readable patchinfo files", so callers that
    already know the approach found a patch (patch_found is True) can treat
    None here as "diffSolutions exists but is unreadable".
    """
    if base_dir is None:
        return None
    diff_dir = Path(base_dir) / f"{project}-{bug_id}" / "astor-output" / "diffSolutions"
    if not diff_dir.is_dir():
        return None
    info_files = sorted(diff_dir.glob("patchinfo_*.json"))
    if not info_files:
        return None

    hunks = []
    for info_file in info_files:
        try:
            data = json.loads(info_file.read_text())
        except (OSError, ValueError):
            continue
        for hunk in data.get("patchhunks", []):
            hunks.append((
                hunk.get("LOCATION", "?"),
                hunk.get("LINE", "?"),
                hunk.get("ORIGINAL_CODE", ""),
                hunk.get("PATCH_HUNK_CODE", ""),
            ))
    return hunks or None


def format_patch(hunks):
    """Render patch hunks as a compact ``file:line`` + before/after block.

    Not a real unified diff: since a hunk always edits one expression to
    another expression in place (same file, same line on both sides), a
    ``--- a/file`` / ``+++ b/file`` pair would just repeat the same filename
    twice, so a single ``file:line`` header is used instead. The header uses
    the bare class name rather than the full package path, and the code
    itself has fully-qualified type names shortened, to keep lines narrow.
    """
    lines = []
    for location, line_no, before, after in hunks:
        filename = location.rsplit(".", 1)[-1] + ".java"
        lines.append(f"{filename}:{line_no}")
        lines.append(f"-{simplify_fqn(unescape_code(before))}")
        lines.append(f"+{simplify_fqn(unescape_code(after))}")
    return "\n".join(lines)


def find_bugs(results_dir, bfs_dir, mlfs_dir, whitelist=None):
    results_path = Path(results_dir)
    if not results_path.is_dir():
        print(f"Error: directory not found: {results_dir}", file=sys.stderr)
        sys.exit(1)

    bugs = []
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
        status = {
            "cardumen": patch_found(results_dir, project, bug_id),
            "bfs": patch_found(bfs_dir, project, bug_id),
            "mlfs": patch_found(mlfs_dir, project, bug_id),
        }
        bugs.append((project, bug_id, status))

    bugs.sort(key=lambda x: (x[0], x[1]))
    return bugs


def matches_filter(status, yes, no):
    """A bug matches if every approach in ``yes`` found a patch (True) and
    every approach in ``no`` did not (False or None, i.e. anything but True)."""
    if any(status[a] is not True for a in yes):
        return False
    if any(status[a] is True for a in no):
        return False
    return True


def status_summary(status):
    marks = []
    for a in APPROACHES:
        s = status[a]
        mark = r"\Checkmark" if s is True else (r"\XSolidBrush" if s is False else "--")
        marks.append(f"{APPROACH_LABELS[a]}: {mark}")
    return r" \quad ".join(marks)


def build_appendix(bugs, args, include_all):
    lines = []
    for project, bug_id, status in bugs:
        found_any = any(status[a] is True for a in APPROACHES)
        if not include_all and not found_any:
            continue

        lines.append(r"\subsection*{" + f"{project}-{bug_id}" + r"}")
        lines.append(status_summary(status) + r"\\[0.5em]")

        if not found_any:
            lines.append(r"\textit{No plausible patch found by any approach.}")
            lines.append("")
            continue

        for a in APPROACHES:
            if status[a] is not True:
                continue
            hunks = read_hunks(approach_dir(args, a), project, bug_id)
            if not hunks:
                continue
            caption = f"{APPROACH_LABELS[a]} patch for {project}-{bug_id}"
            lines.append(
                r"\begin{lstlisting}[" + LSTLISTING_OPTS + ",caption={" + caption + r"}]"
            )
            lines.append(format_patch(hunks))
            lines.append(r"\end{lstlisting}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main():
    parser = argparse.ArgumentParser(
        description="Generate a LaTeX appendix of patch diffs from d4j-cardumen-results."
    )
    parser.add_argument(
        "results_dir",
        nargs="?",
        default="d4j-cardumen-results",
        help="Path to the Cardumen results directory (default: d4j-cardumen-results)",
    )
    parser.add_argument("output", nargs="?", help="Output .tex file (default: stdout)")
    parser.add_argument("--copy", action="store_true", help="Copy the appendix to the clipboard")
    parser.add_argument(
        "--all", action="store_true",
        help="Include bugs with no patch from any approach (default: skip them)",
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
        help="Path to a whitelist file (one '<Project> <ID>' per line); "
             "only listed bugs are included",
    )
    parser.add_argument(
        "-y", "--found",
        dest="yes", action="append", default=[], type=str.lower, choices=APPROACHES,
        metavar="APPROACH",
        help="Only include bugs where APPROACH found a plausible patch "
             "(cardumen, bfs, mlfs); repeatable",
    )
    parser.add_argument(
        "-n", "--not-found",
        dest="no", action="append", default=[], type=str.lower, choices=APPROACHES,
        metavar="APPROACH",
        help="Only include bugs where APPROACH did not find a plausible patch "
             "(cardumen, bfs, mlfs); repeatable",
    )
    args = parser.parse_args()

    overlap = set(args.yes) & set(args.no)
    if overlap:
        parser.error(
            f"approach(es) given to both -y and -n: {', '.join(sorted(overlap))}"
        )

    whitelist = load_whitelist(args.whitelist) if args.whitelist else None
    bugs = find_bugs(args.results_dir, args.bfs_dir, args.mlfs_dir, whitelist)
    if not bugs:
        print("Warning: no <Project>-<ID> directories found.", file=sys.stderr)

    bugs = [b for b in bugs if matches_filter(b[2], args.yes, args.no)]
    if not bugs:
        print("Warning: no bugs matched the given filters.", file=sys.stderr)

    appendix = build_appendix(bugs, args, include_all=args.all)

    if args.output:
        Path(args.output).write_text(appendix)
        print(f"Written to {args.output}")
    else:
        print(appendix)

    if args.copy:
        cmd = copy_to_clipboard(appendix)
        if cmd:
            print(f"Copied to clipboard via {cmd}.", file=sys.stderr)


if __name__ == "__main__":
    main()