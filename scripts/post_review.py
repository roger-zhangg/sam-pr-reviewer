#!/usr/bin/env python3
"""Parse Kiro CLI review output and post as a GitHub PR review with inline comments.

Expects the review output format from SKILL.md:
    #### N. [CATEGORY] `file_path:line_number`
    comment body...

Posts via GitHub REST API as a COMMENT review (not APPROVE or REQUEST_CHANGES).
"""

import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.error

COMMENT_PATTERN = re.compile(
    r"^####\s+\d+\.\s+\[([A-Z_]+)\]\s+`([^:]+):(\d+)`",
    re.MULTILINE,
)
REPO_PATTERN = re.compile(r"^[a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+$")
API_BASE = "https://api.github.com"

SECRET_PATTERNS = [
    re.compile(r"ghp_[A-Za-z0-9]{36,}"),                          # GitHub PAT
    re.compile(r"ghs_[A-Za-z0-9]{36,}"),                          # GitHub App token
    re.compile(r"gho_[A-Za-z0-9]{36,}"),                          # GitHub OAuth token
    re.compile(r"github_pat_[A-Za-z0-9_]{22,}"),                  # Fine-grained PAT
    re.compile(r"glpat-[A-Za-z0-9\-_]{20,}"),                     # GitLab PAT
    re.compile(r"AKIA[0-9A-Z]{16}"),                               # AWS access key
    re.compile(r"(?:sk-|sk-proj-)[A-Za-z0-9]{20,}"),              # OpenAI key
    re.compile(r"(?:key|token|secret|password|api[_-]?key|credential)\s*[=:]\s*['\"]?\S{12,}", re.I),
]


def sanitize_review_text(text):
    """Redact potential secrets from review text before posting publicly."""
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def parse_review(text):
    """Extract inline comments from the review output."""
    comments = []
    matches = list(COMMENT_PATTERN.finditer(text))

    for i, m in enumerate(matches):
        category = m.group(1)
        file_path = m.group(2)
        line_number = int(m.group(3))

        # Body is everything between this header and the next (or end)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()

        # Remove trailing --- separator
        body = re.sub(r"\n---\s*$", "", body).strip()

        if body:
            comments.append({
                "path": file_path,
                "line": line_number,
                "body": f"**[{category}]** {body}",
            })

    return comments


def build_summary(text, comment_count):
    """Extract or build a summary body for the review."""
    # Try to extract the header section
    lines = []
    for line in text.split("\n"):
        if line.startswith("### Comments") or line.startswith("#### "):
            break
        lines.append(line)

    header = "\n".join(lines).strip()
    if header:
        return header

    if comment_count == 0:
        return "✅ **SAM PR Reviewer**: No issues found. The changes look good."

    return f"🔍 **SAM PR Reviewer**: Found {comment_count} issue(s). See inline comments below."


def github_api(method, path, token, data=None):
    """Make a GitHub API request."""
    url = f"{API_BASE}{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else ""
        print(f"GitHub API error {e.code}: {error_body}", file=sys.stderr)
        raise


def get_diff_lines(token, repo, pr_number, commit_sha):
    """Get the set of (file_path, line_number) that are valid for inline comments.

    GitHub only allows inline comments on lines that appear in the diff.
    """
    valid = set()
    page = 1
    while True:
        files = github_api(
            "GET",
            f"/repos/{repo}/pulls/{pr_number}/files?per_page=100&page={page}",
            token,
        )
        if not files:
            break
        for f in files:
            path = f["filename"]
            patch = f.get("patch", "")
            line_num = 0
            for line in patch.split("\n"):
                hunk = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)", line)
                if hunk:
                    line_num = int(hunk.group(1))
                    continue
                if line.startswith("+"):
                    valid.add((path, line_num))
                    line_num += 1
                elif line.startswith("-"):
                    pass  # removed lines don't have a new-side number
                else:
                    line_num += 1
        page += 1
    return valid


def post_review(repo, pr_number, commit_sha, token, review_text):
    """Post a PR review with inline comments."""
    review_text = sanitize_review_text(review_text)
    comments = parse_review(review_text)
    summary = build_summary(review_text, len(comments))

    # Get valid diff lines to filter out comments on non-diff lines
    valid_lines = get_diff_lines(token, repo, pr_number, commit_sha)

    inline_comments = []
    fallback_comments = []

    for c in comments:
        if (c["path"], c["line"]) in valid_lines:
            inline_comments.append({
                "path": c["path"],
                "line": c["line"],
                "body": c["body"],
            })
        else:
            # Can't post inline — append to summary
            fallback_comments.append(
                f"**[{c['path']}:{c['line']}]** {c['body']}"
            )

    if fallback_comments:
        summary += "\n\n---\n**Comments on lines outside the diff:**\n\n"
        summary += "\n\n".join(fallback_comments)

    review_data = {
        "commit_id": commit_sha,
        "body": summary,
        "event": "COMMENT",
        "comments": inline_comments,
    }

    github_api(
        "POST",
        f"/repos/{repo}/pulls/{pr_number}/reviews",
        token,
        review_data,
    )

    total = len(inline_comments) + len(fallback_comments)
    print(f"Posted review: {len(inline_comments)} inline, {len(fallback_comments)} in summary, {total} total")


def main():
    parser = argparse.ArgumentParser(description="Post code review to GitHub PR")
    parser.add_argument("--repo", required=True, help="owner/repo")
    parser.add_argument("--pr", required=True, type=int, help="PR number")
    parser.add_argument("--commit", required=True, help="Head commit SHA")
    parser.add_argument("--review-file", required=True, help="Path to review output file")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Error: GITHUB_TOKEN environment variable not set", file=sys.stderr)
        sys.exit(1)

    if not REPO_PATTERN.match(args.repo):
        print(f"Error: Invalid repo format: {args.repo}", file=sys.stderr)
        sys.exit(1)

    with open(args.review_file) as f:
        review_text = f.read()

    if not review_text.strip():
        print("Review output is empty, posting summary only.")
        review_text = "## Code Review Results\n✅ No issues found. The changes look good."

    post_review(args.repo, args.pr, args.commit, token, review_text)


if __name__ == "__main__":
    main()
