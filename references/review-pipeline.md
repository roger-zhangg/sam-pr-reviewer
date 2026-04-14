# Review Pipeline

5-pass review pipeline for thorough, high-quality code review.

## Pass 1: Generate Initial Comments

Review the parsed diff JSON and produce comments. Apply the coding guidelines
from `references/coding-guidelines.md` and any custom guidelines provided.

**For large diffs, use `--summary` first, then review file-by-file:**

1. Run `parse_diff.py --summary` to get the file list and stats
2. Group files logically (by directory, component, or relatedness) into max 5 groups
3. For each group, run `parse_diff.py --file <path>` for each file and review the group together
4. Combine all comments from all groups

**For cross-file context** (e.g., checking if an interface change breaks callers):
- Read full file content at a revision: `git show <commit>:<path>`
- These are useful during the confidence check pass to verify comments against full file context

For each issue found, produce a comment with:
- `file_path`: the `to_path` from the diff
- `line_number`: a visible new-side line number from the relevant hunk
- `comment`: markdown-formatted feedback with code examples where helpful
- `category`: one of: `BUG`, `SECURITY`, `ERROR_HANDLING`, `INPUT_VALIDATION`, `PERFORMANCE`, `CONCURRENCY`, `RESOURCE_MANAGEMENT`, `NAMING`, `STYLE`, `DOCUMENTATION`, `TESTING`, `GENERAL`

If custom rules were loaded from `kiro-review.yaml`, apply them as additional
review criteria. Only apply rules whose `file-patterns` match the files being reviewed.

## Pass 2: Deduplicate

Remove duplicate and merge similar comments:
- Merge by similarity of the **issue identified**, not by code location
- When merging, keep the file location from one comment
- Combine relevant context from all merged comments

## Pass 3: Confidence Check

For each comment, validate it against the actual code:

1. Find and quote the specific diff lines relevant to the comment
2. Pay attention to which lines are added (+) vs removed (-)
3. Verify the comment identifies a legitimate, concrete issue

**Discard** comments that:
- Are incorrect or misunderstand the code
- Are nitpicking or low-priority
- Don't identify a concrete problem needing a fix
- Are speculative about problems without direct evidence in the diff

**Important**: A comment about consequences of a visible code pattern IS concrete — not
speculative — **only if** the consequence is a widely recognized, well-documented failure mode
of that specific pattern (e.g., SQL injection from string concatenation, race conditions from
unsynchronized shared state). A hypothetical chain of events or an unlikely edge case still
counts as speculative and should be discarded.

**Additional context-sensitive checks:**
- If comment mentions time/dates/future: consider current system time before flagging
- **Do NOT assume existing codebase patterns are correct.** Evaluate each code pattern on its
  own merits. Existing code may contain latent bugs that should not be propagated into new code.

## Pass 4: Guideline Compliance

Re-check each surviving comment against the coding guidelines. Discard any that:
- Contradict the guidelines
- Fall below the minimum severity threshold (discard pure style nits unless they affect readability)

## Pass 5: Refine

For each final comment:
1. Ensure any code examples are correct and follow best practices
2. Remove code examples that make uncertain assumptions
3. Format with markdown for clarity — use fenced code blocks for code
4. Keep code examples brief yet clear
5. Ensure the comment explains **why** the change is needed (concrete problem that could occur)
