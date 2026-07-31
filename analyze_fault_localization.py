#!/usr/bin/env python3
"""For each single-line bug, determine whether the developer patch location was
(a) flagged by ASTOR's spectrum fault localization, and (b) turned into a
modification point (the space ASTOR actually searched).

Two signals per bug:
  * ``fl_flagged``  -- dev line appears in the raw "Suspicious:" list logged by
    the fault localizer (run.log).
  * ``mod_point``   -- dev line appears in suspicious_<bug>.json, which Astor
    writes from originalVariant.getModificationPoints(): the deduplicated set of
    suspicious lines it could actually turn into a modification point and mutate.

Defects4J *.src.patch transforms fixed(a) -> buggy(b); Astor runs on the buggy
b-side, so the developer-touched buggy lines are the patch's '+' line numbers.
"""
import re
import sys
from pathlib import Path

from generate_results_table import load_whitelist, patch_found

D4J_HOME = Path("/home/geest/thesis/defects4j-2.0")
RESULT_DIRS = [
    ("cardumen", Path("d4j-cardumen-results")),
    ("bfs", Path("d4j-cardumen-bfs-results")),
    ("mlfs", Path("d4j-cardumen-mlfs-results")),
]

SUSP_LOG_RE = re.compile(r"^Suspicious:.*line\s+(\S+)\s+l:\s*(\d+)")


def run_status(project, bug_id):
    """Best run status across approaches: done / error / incomplete / not-run."""
    best = "not-run"
    order = {"not-run": 0, "incomplete": 1, "error": 2, "done": 3}
    for _, base in RESULT_DIRS:
        run = base / f"{project}-{bug_id}"
        if not run.is_dir():
            st = "not-run"
        elif (run / ".done").is_file():
            st = "done"
        elif (run / ".error").is_file():
            st = "error"
        else:
            st = "incomplete"
        if order[st] > order[best]:
            best = st
    return best


def mod_points(project, bug_id):
    """(label, set of (class,line)) from suspicious_<bug>.json, or (None, None)."""
    for label, base in RESULT_DIRS:
        for js in (base / f"{project}-{bug_id}").glob("astor-output/*/suspicious_*.json"):
            entries = set()
            for line in js.read_text().splitlines():
                p = line.strip().split(",")
                if len(p) >= 2:
                    try:
                        entries.add((p[0], int(p[1])))
                    except ValueError:
                        pass
            if entries:
                return label, entries
    return None, None


def fl_flagged(project, bug_id):
    """(label, set of (class,line)) from the raw 'Suspicious:' log lines."""
    for label, base in RESULT_DIRS:
        log = base / f"{project}-{bug_id}" / "run.log"
        if not log.is_file():
            continue
        entries = set()
        for line in log.read_text(errors="replace").splitlines():
            m = SUSP_LOG_RE.match(line)
            if m:
                try:
                    entries.add((m.group(1), int(m.group(2))))
                except ValueError:
                    pass
        if entries:
            return label, entries
    return None, None


def dev_patch_locations(project, bug_id):
    """List of (buggy_file_path, set_of_plus_lines) hunks, or None if no patch."""
    pf = D4J_HOME / "framework" / "projects" / project / "patches" / f"{bug_id}.src.patch"
    if not pf.is_file():
        return None
    results = []
    cur_file, b_line, plus = None, 0, set()

    def flush():
        nonlocal plus
        if cur_file is not None and plus:
            results.append((cur_file, set(plus)))
        plus = set()

    for line in pf.read_text().splitlines():
        if line.startswith("+++ "):
            flush()
            m = line[4:].strip()
            cur_file = m[2:] if m.startswith("b/") else m
        elif line.startswith("--- ") or line.startswith("diff "):
            continue
        elif line.startswith("@@"):
            flush()
            mm = re.search(r"\+(\d+)", line)
            b_line = int(mm.group(1)) if mm else 0
        elif line.startswith("+"):
            plus.add(b_line)
            b_line += 1
        elif line.startswith("-"):
            pass
        else:
            b_line += 1
    flush()
    return results


def loc_in(entries, locs):
    if not entries or not locs:
        return False
    for f, plus in locs:
        for (cls, ln) in entries:
            outer = cls.split("$")[0]
            if ln in plus and f.endswith(outer.replace(".", "/") + ".java"):
                return True
    return False


def analyse(whitelist_path="single-line-bugs.txt"):
    """Return a list of per-bug records with the FL / modification-point verdict."""
    whitelist = sorted(load_whitelist(whitelist_path), key=lambda x: (x[0], x[1]))
    rows = []
    for project, bug_id in whitelist:
        locs = dev_patch_locations(project, bug_id)
        _, mp = mod_points(project, bug_id)
        _, fl = fl_flagged(project, bug_id)
        status = run_status(project, bug_id)
        rows.append({
            "project": project,
            "bug_id": bug_id,
            "bug": f"{project}-{bug_id}",
            "status": status,
            "fl_any": fl is not None,
            "mp_any": mp is not None,
            "fl_hit": loc_in(fl, locs),
            "mp_hit": loc_in(mp, locs),
        })
    return rows


def main():
    rows = analyse()

    # cross-tab
    from collections import Counter
    c = Counter((r["fl_hit"], r["mp_hit"]) for r in rows)
    print("fl_hit, mp_hit -> count")
    for k in sorted(c, reverse=True):
        print(f"  FL={k[0]!s:5} MP={k[1]!s:5} -> {c[k]}")
    print()
    # divergence: FL flagged but not a modification point
    print("=== FL flagged the dev line but it is NOT a modification point ===")
    for r in rows:
        if r["fl_hit"] and not r["mp_hit"]:
            print(f"  {r['bug']:<18} status={r['status']}")
    print()
    print("=== No FL suspicious list at all (status breakdown) ===")
    from collections import Counter as C2
    st = C2(r["status"] for r in rows if not r["fl_any"])
    print(" ", dict(st))
    for r in rows:
        if not r["fl_any"]:
            print(f"  {r['bug']:<18} status={r['status']} mp_any={r['mp_any']}")
    print()
    n = len(rows)
    print(f"Total bugs: {n}")
    print(f"MP hit (had a chance): {sum(r['mp_hit'] for r in rows)}")
    print(f"FL hit: {sum(r['fl_hit'] for r in rows)}")


if __name__ == "__main__":
    main()