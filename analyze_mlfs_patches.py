#!/usr/bin/env python3
"""
Assemble a per-bug comparison bundle for MLFS-only patches.

Target set: bugs that are on a whitelist, were patched by MLFS, and were *not*
patched by Cardumen (the same selection as
``generate_diff_appendix.py -y mlfs -n cardumen``). For each such bug this lays
the MLFS patch, the Defects4J developer patch, and Cardumen's run outcome
side-by-side so that overfitting (MLFS patch vs developer patch) and the reason
MLFS succeeded where Cardumen did not can be judged by hand.

It does NOT decide correctness itself: it emits a machine-readable JSON with an
auto-category *hint* (based on the shape of the MLFS replacement expression) plus
a human-readable markdown bundle. The final correct/overfit verdict and the
"why MLFS won" category are filled in by the analyst in the report.

Usage:
    python3 analyze_mlfs_patches.py                 # markdown to stdout
    python3 analyze_mlfs_patches.py --out bundle.md # ... and to a file
    python3 analyze_mlfs_patches.py --json data.json

The developer patches come from a Defects4J checkout; override its location with
--d4j-home or the D4J_HOME environment variable.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

from generate_diff_appendix import read_hunks, format_patch, approach_dir
from generate_results_table import patch_found, load_whitelist

DEFAULT_D4J_HOME = "/home/geest/thesis/defects4j-2.0"
DEFAULT_WHITELIST = "single-line-bugs.txt"


def cardumen_outcome(results_dir, project, bug_id):
    """Distinguish *how* Cardumen failed to patch the bug.

    ``exhausted`` -> a ``.done`` marker (ran to completion, found nothing);
    ``crashed``   -> an ``.error`` marker; ``incomplete`` -> ran but no marker
    (killed/interrupted); ``not-run`` -> no directory at all.
    """
    run_dir = Path(results_dir) / f"{project}-{bug_id}"
    if not run_dir.is_dir():
        return "not-run"
    if (run_dir / ".error").is_file():
        return "crashed"
    if (run_dir / ".done").is_file():
        return "exhausted"
    return "incomplete"


def dev_patch(d4j_home, project, bug_id):
    """Return the developer source patch text for a bug, or None if absent."""
    patch_file = Path(d4j_home) / "framework" / "projects" / project / "patches" / f"{bug_id}.src.patch"
    try:
        return patch_file.read_text()
    except OSError:
        return None


# A replacement whose expression nests a call/constructor inside another
# call/constructor's argument list is outside flat Cardumen's single-template,
# atomic-hole search space. We approximate that structure without a real Java
# parser: a token that opens a call/new immediately (ignoring bare grouping
# parens) whose argument region itself contains another call/new.
CALL_RE = re.compile(r'(?:new\s+[\w.]+|\b[\w.]+)\s*\(')


def categorise_hint(patch_hunk_code):
    """Heuristic first-pass category for why MLFS could synthesise the patch.

    Returns one of ``nested``, ``context-call``, ``flat``. This is only a hint:
    ``nested`` strongly implies compositional synthesis (Cardumen cannot do it);
    ``flat`` implies the fix shape was in Cardumen's reach, so the reason is more
    likely search ordering/budget or a Cardumen crash.
    """
    code = patch_hunk_code.strip()
    calls = list(CALL_RE.finditer(code))
    if not calls:
        return "flat"  # variable/literal/field swap
    # A call whose argument list contains a further call/new is a nested compose.
    for m in calls:
        depth = 0
        for other in calls:
            if other is m:
                continue
            # other call opens after this call's "(" -> it is (roughly) an argument
            if other.start() > m.end() - 1:
                depth += 1
        if depth:
            return "nested"
    return "context-call"  # single call/new with atomic arguments


def collect(args):
    whitelist = load_whitelist(args.whitelist)
    cardumen_dir = args.results_dir
    mlfs_dir = args.mlfs_dir

    bugs = []
    for project, bug_id in sorted(whitelist, key=lambda x: (x[0], x[1])):
        mlfs_status = patch_found(mlfs_dir, project, bug_id)
        cardumen_status = patch_found(cardumen_dir, project, bug_id)
        # -y mlfs -n cardumen: MLFS found (True), Cardumen did not (not True).
        if mlfs_status is not True or cardumen_status is True:
            continue

        hunks = read_hunks(mlfs_dir, project, bug_id) or []
        record = {
            "project": project,
            "bug_id": bug_id,
            "bug": f"{project}-{bug_id}",
            "mlfs_diff": format_patch(hunks) if hunks else "",
            "hunks": [
                {
                    "location": loc,
                    "line": line,
                    "original_code": before,
                    "patch_hunk_code": after,
                }
                for (loc, line, before, after) in hunks
            ],
            "cardumen_outcome": cardumen_outcome(cardumen_dir, project, bug_id),
            "dev_patch": dev_patch(args.d4j_home, project, bug_id),
            "category_hint": categorise_hint(
                " ".join(h[3] for h in hunks)
            ) if hunks else "unknown",
            "category": "TODO",
            "verdict": "TODO",
        }
        bugs.append(record)
    return bugs


def render_markdown(bugs):
    out = ["# MLFS-only patches: overfitting + why-MLFS-won bundle", ""]
    out.append(f"{len(bugs)} bugs: MLFS patched, Cardumen did not, on whitelist.")
    out.append("")
    for b in bugs:
        out.append(f"## {b['bug']}")
        out.append("")
        out.append(f"- Cardumen outcome: **{b['cardumen_outcome']}**")
        out.append(f"- Auto category hint: **{b['category_hint']}**")
        out.append("")
        out.append("**MLFS patch:**")
        out.append("```diff")
        out.append(b["mlfs_diff"] or "(no readable hunks)")
        out.append("```")
        out.append("")
        out.append("**Developer patch:**")
        out.append("```diff")
        out.append((b["dev_patch"] or "(developer patch not found)").rstrip())
        out.append("```")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--results-dir", default="d4j-cardumen-results",
                        help="Cardumen results directory (default: d4j-cardumen-results)")
    parser.add_argument("--mlfs-dir", default="d4j-cardumen-mlfs-results",
                        help="MLFS results directory (default: d4j-cardumen-mlfs-results)")
    parser.add_argument("--whitelist", default=DEFAULT_WHITELIST,
                        help=f"Whitelist file (default: {DEFAULT_WHITELIST})")
    parser.add_argument("--d4j-home", default=os.environ.get("D4J_HOME", DEFAULT_D4J_HOME),
                        help="Defects4J home (default: $D4J_HOME or " + DEFAULT_D4J_HOME + ")")
    parser.add_argument("--out", help="Write the markdown bundle to this file")
    parser.add_argument("--json", help="Write the machine-readable data to this file")
    args = parser.parse_args()

    bugs = collect(args)
    if not bugs:
        print("Warning: no bugs matched (MLFS found, Cardumen not, on whitelist).",
              file=sys.stderr)

    markdown = render_markdown(bugs)
    if args.out:
        Path(args.out).write_text(markdown)
        print(f"Wrote markdown bundle to {args.out}", file=sys.stderr)
    else:
        print(markdown)

    if args.json:
        Path(args.json).write_text(json.dumps(bugs, indent=2))
        print(f"Wrote data to {args.json}", file=sys.stderr)


if __name__ == "__main__":
    main()
