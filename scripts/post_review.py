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
    r"^####\s+\d+\.\s+\[([A-Z_]+)\]\s+`?([^:`\s]+):(\d+)`?",
    re.MULTILINE,
)
REPO_PATTERN = re.compile(r"^[a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+$")
API_BASE = "https://api.github.com"

ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def strip_ansi(text):
    """Remove ANSI escape codes from text."""
    return ANSI_ESCAPE.sub("", text)


# Pattern for code blocks that lost their fences during terminal rendering.
# Kiro renders ```python\ncode\n``` as just "python\ncode\n" with possible
# surrounding box-drawing characters (━).
BARE_CODE_BLOCK = re.compile(
    r"(?m)^(python|javascript|typescript|java|yaml|bash|json|go|rust|ruby|c|cpp|csharp|shell|sql|html|css|xml|toml|hcl|dockerfile)\n(.*?)(?=\n━|\n\n[A-Z]|\n####|\Z)",
    re.DOTALL,
)


def restore_code_fences(text):
    """Re-wrap bare code blocks that lost their triple-backtick fences."""
    def replacer(m):
        lang = m.group(1)
        code = m.group(2).rstrip()
        return f"```{lang}\n{code}\n```"
    return BARE_CODE_BLOCK.sub(replacer, text)


def extract_review(text):
    """Extract the final '## Code Review Results' section from kiro-cli output.

    Kiro outputs intermediate tool calls and thinking before the final review.
    We only want the last review section.
    """
    marker = "## Code Review Results"
    idx = text.rfind(marker)
    if idx != -1:
        return text[idx:]
    return "## Code Review Results\n⚠️ Review output could not be parsed. Check the action logs."


CODEBLOCK_TAG = re.compile(
    r'<codeblock(?:\s+lang="([^"]*)")?\s*>(.*?)</codeblock>',
    re.DOTALL,
)
INLINE_CODE_TAG = re.compile(r'<code>(.*?)</code>', re.DOTALL)


def convert_xml_to_markdown(text):
    """Convert XML-style code tags back to GitHub-flavored markdown."""
    text = CODEBLOCK_TAG.sub(lambda m: f"```{m.group(1) or ''}\n{m.group(2).strip()}\n```", text)
    text = INLINE_CODE_TAG.sub(r'`\1`', text)
    # Also strip box-drawing separator lines
    text = re.sub(r'\n?━+\n?', '\n', text)
    return text


SECRET_PATTERNS = [
    re.compile(r"ksk_[A-Za-z0-9]{20,}"),                          # Kiro API key
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

        # Remove trailing --- separator and box-drawing lines
        body = re.sub(r"\n---\s*$", "", body).strip()
        body = re.sub(r"\n?━+\n?", "", body).strip()

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
    review_text = strip_ansi(review_text)
    review_text = extract_review(review_text)
    review_text = convert_xml_to_markdown(review_text)
    review_text = sanitize_review_text(review_text)
    comments = parse_review(review_text)

    # Debug: show what was extracted
    print(f"Extracted review length: {len(review_text)} chars")
    print(f"Parsed {len(comments)} comments from review text")
    if not comments:
        # Show first 500 chars to help debug
        print(f"Review text preview:\n{review_text[:500]}")

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

    try:
        github_api(
            "POST",
            f"/repos/{repo}/pulls/{pr_number}/reviews",
            token,
            review_data,
        )
    except urllib.error.HTTPError as e:
        if e.code == 403:
            print("::warning::Cannot post review — token lacks write access. "
                  "This is expected for fork PRs to upstream repos.", file=sys.stderr)
            return
        raise

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
