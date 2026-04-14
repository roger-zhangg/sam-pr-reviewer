#!/usr/bin/env python3
"""Parse git diffs into structured JSON for code review.

Usage:
    parse_diff.py --from BASE_SHA --to HEAD_SHA [--directory DIR]
    parse_diff.py --summary --from BASE_SHA --to HEAD_SHA
    parse_diff.py --file PATH --from BASE_SHA --to HEAD_SHA
"""

import argparse
import json
import os
import re
import subprocess
import sys

FILE_OMIT_THRESHOLD = 200000
IGNORED_PATTERNS = [
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "Pipfile.lock", "poetry.lock", "Gemfile.lock",
    "composer.lock", "Cargo.lock", "go.sum",
]
HUNK_PATTERN = re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def run_git(args, cwd="."):
    result = subprocess.run(
        ["git"] + args, cwd=cwd, capture_output=True, text=True, errors="replace"
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "not a git repository" in stderr.lower():
            print(json.dumps({
                "error": "not_a_git_repository",
                "message": f"Directory '{cwd}' is not a git repository.",
                "directory": cwd
            }))
            sys.exit(1)
        print(json.dumps({"error": f"git {' '.join(args)}: {stderr}"}))
        sys.exit(1)
    return result.stdout


def _should_ignore(from_path, to_path):
    for pattern in IGNORED_PATTERNS:
        if (to_path or "").endswith(pattern) or (from_path or "").endswith(pattern):
            return True
    return False


def _strip_prefix(path):
    return path[2:] if path.startswith(("a/", "b/")) else path


def parse_diff(diff_text):
    """Parse unified diff into structured diffs list and omitted_files list."""
    sections = []
    current = []
    for line in diff_text.split("\n"):
        if line.startswith("diff --git"):
            if current:
                sections.append("\n".join(current))
            current = []
        current.append(line)
    if current:
        sections.append("\n".join(current))

    diffs = []
    omitted = []
    hunk_id = 0

    for section in sections:
        lines = section.split("\n")
        from_path = to_path = None

        for line in lines:
            if line.startswith("--- "):
                p = line[4:].strip()
                from_path = None if p == "/dev/null" else _strip_prefix(p)
            elif line.startswith("+++ "):
                p = line[4:].strip()
                to_path = None if p == "/dev/null" else _strip_prefix(p)

        if not from_path and not to_path:
            continue
        if _should_ignore(from_path, to_path):
            continue
        if "Binary files" in section:
            continue

        hunks = []
        i = 0
        while i < len(lines):
            m = HUNK_PATTERN.match(lines[i]) if lines[i].startswith("@@") else None
            if not m:
                i += 1
                continue

            new_start = int(m.group(3))
            hunk_id += 1
            hunk_lines = []
            line_num = new_start
            i += 1

            while i < len(lines):
                l = lines[i]
                if l.startswith(("@@", "diff --git")):
                    break
                if l.startswith("+"):
                    hunk_lines.append({"line_number": line_num, "line": l})
                    line_num += 1
                elif l.startswith("-"):
                    hunk_lines.append({"line_number": "N/A", "line": l})
                elif l.startswith(" "):
                    hunk_lines.append({"line_number": line_num, "line": l})
                    line_num += 1
                i += 1

            if hunk_lines:
                hunks.append({"id": hunk_id, "lines": hunk_lines})

        if not hunks:
            continue

        diff_size = sum(len(json.dumps(h)) for h in hunks)
        file_path = to_path or from_path
        if diff_size > FILE_OMIT_THRESHOLD:
            omitted.append(file_path)
            hunks = [{"id": hunk_id + 1, "lines": [
                {"line_number": "N/A", "line": "*** Omitted: diff exceeds size threshold ***"}
            ]}]
            hunk_id += 1

        diffs.append({"from_path": from_path, "to_path": to_path, "hunks": hunks})

    return diffs, omitted


def main():
    parser = argparse.ArgumentParser(description="Parse git diffs for PR code review")
    parser.add_argument("--from", dest="from_ref", required=True, help="Base commit SHA")
    parser.add_argument("--to", dest="to_ref", required=True, help="Head commit SHA")
    parser.add_argument("--summary", action="store_true", help="File list with stats only")
    parser.add_argument("--file", dest="file_path", default=None, help="Diff for a single file")
    parser.add_argument("--directory", default=".", help="Repository directory")

    args = parser.parse_args()
    cwd = os.path.abspath(args.directory)
    from_ref = args.from_ref
    to_ref = args.to_ref

    # Validate refs are hex SHAs to prevent flag injection
    sha_pattern = re.compile(r"^[0-9a-f]{4,40}$")
    if not sha_pattern.match(from_ref) or not sha_pattern.match(to_ref):
        print(json.dumps({"error": "Invalid git ref format — expected hex SHA"}))
        sys.exit(1)

    # Ensure both refs are available
    run_git(["rev-parse", "--verify", from_ref], cwd)
    run_git(["rev-parse", "--verify", to_ref], cwd)

    branch = run_git(["branch", "--show-current"], cwd).strip() or "detached"

    if args.summary:
        stat_output = run_git(["diff", "--stat", from_ref, to_ref], cwd)
        files = [f for f in run_git(["diff", "--name-only", from_ref, to_ref], cwd).strip().splitlines() if f]
        print(json.dumps({
            "summary": True,
            "reviewed": f"{from_ref[:8]}..{to_ref[:8]}",
            "branch": branch,
            "file_count": len(files),
            "files": files,
            "stat": stat_output.strip()
        }, indent=2))
        return

    if args.file_path:
        diff_text = run_git(["diff", from_ref, to_ref, "--", args.file_path], cwd)
        if not diff_text.strip():
            print(json.dumps({"error": f"No changes found for file: {args.file_path}"}))
            return
    else:
        diff_text = run_git(["diff", from_ref, to_ref], cwd)
        if not diff_text.strip():
            print(json.dumps({"error": "No changes found to review"}))
            return

    diffs, omitted = parse_diff(diff_text)

    if not diffs:
        print(json.dumps({"error": "No reviewable changes found"}))
        return

    repo_name = os.path.basename(cwd)
    output = {
        "packages": [{
            "package": repo_name,
            "commit": {"message": f"{from_ref[:8]}..{to_ref[:8]}", "id": to_ref},
            "branch": branch,
            "diffs": diffs,
            "omitted_files": omitted
        }]
    }

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
