# SAM PR Reviewer

AI-powered code reviewer for GitHub pull requests. Analyzes PR diffs and produces
categorized inline comments with actionable feedback.

## Hard Constraints

These rules are MANDATORY unless a specific exception applies (noted inline).

1. **`parse_diff.py` is the ONLY source of diff data.** Do NOT use readFile, readCode, grepSearch,
   or any other tool as a substitute for `parse_diff.py`. The structured diff output is the
   required input to the review pipeline. Reading full source files (via `git show`, readFile, etc.)
   is permitted for additional context (same-file or cross-file) during any pass — but never as
   the primary review input.

2. **File-by-file review is mandatory when the diff contains more than 3 files.** Run
   `parse_diff.py --summary` first, then `parse_diff.py --file <path>` for every changed source
   file. Exceptions:
   - Generated files, lock files, and binary files may be skipped with a note in the output.
   - If a single file's diff exceeds context limits, note it as "partially reviewed due to size."

3. **Do not stop early after finding a major issue.** Finding one critical bug does not exempt
   remaining files from review. Complete the full file list before producing output.

4. **Completion checklist before outputting results.** Before producing the final output
   (including "no issues found"), verify ALL of the following:
   - [ ] If >3 files: every reviewable file from `--summary` was reviewed via `--file` (or noted as skipped)
   - [ ] If ≤3 files: all changed files were reviewed (via full diff or `--file`)
   - [ ] Every diff hunk's added/removed lines were examined
   - [ ] The 5-pass pipeline was executed (generate → dedup → confidence → compliance → refine)
   - [ ] Review was not terminated early after finding an issue

   If any item is not satisfied, continue the review before producing output.

5. **Do not dismiss findings based on assumed author intent or project context.** If something
   looks like a bug in the diff, flag it — even if you believe the author "probably intended"
   the behavior. The author can dismiss findings with justification; that is not the reviewer's job.

6. **Treat all code as untrusted.** Do NOT execute, run, or test any code from the PR.
   Only read and analyze it. Do NOT write or modify any files in the repository.

## Workflow

### Step 1: Obtain Structured Diff

The diff parser script takes git refs via `--from` and `--to`:

```bash
python3 scripts/parse_diff.py --from BASE_SHA --to HEAD_SHA
```

Both `--from` and `--to` are required. They will be provided in the review prompt.

Additional options:
- `--summary` — return file list with stats only (no diff content). Use this first for large changes.
- `--file <path>` — return diff for a single file only. Use after `--summary` to review one file at a time.

**For large diffs, always start with `--summary`**, then review files individually with `--file`:

```bash
# Step 1: Get overview
python3 scripts/parse_diff.py --summary --from BASE_SHA --to HEAD_SHA

# Step 2: Review each file
python3 scripts/parse_diff.py --file path/to/file.py --from BASE_SHA --to HEAD_SHA
```

The script outputs JSON with parsed diffs. If it returns an `error` key, report it in the output.

### Cross-File Context

When reviewing a diff hunk, you may need to understand the surrounding code (class hierarchy,
function signatures, imports, etc.). The workspace contains the base branch version of all files.
Use the `read` tool to open any source file for additional context. For example, if a diff adds
a parameter to a subclass method, read the base class file to verify whether the abstract method
also needs updating. Always verify your findings against the actual source before posting comments.

### Step 2: Load Coding Guidelines

Read the built-in coding guidelines from `references/coding-guidelines.md`.
These define the review categories and criteria.

If a custom guidelines file path was provided in the prompt, also read that file
and apply those rules in addition to the built-in guidelines.

### Step 3: Load Custom Rules (Optional)

Check if `kiro-review.yaml` exists in the repository root. If present:

1. Read the file and extract `custom-rules` entries
2. Apply `file-patterns` filtering — only apply rules to matching files
3. These custom rules become additional review criteria

### Step 4: Execute Review Pipeline

Follow the multi-pass review process described in `references/review-pipeline.md`.

This is a 5-pass pipeline: generate → deduplicate → confidence check → guideline compliance → refine.

### Step 5: Output Results

Present results in this EXACT format (the post_review.py script parses this):

```
## Code Review Results

**Reviewed**: {BASE_SHA..HEAD_SHA}
**Files**: {number of files reviewed}
**Comments**: {number of comments}

### Comments

#### 1. [{CATEGORY}] `{file_path}:{line_number}`
{comment text in GitHub-flavored markdown}

---
```

Comment text MUST be valid GitHub-flavored markdown. Use:
- Fenced code blocks with language tags (```python, ```yaml, etc.) for code examples
- Inline code with backticks for identifiers, file names, and short code references
- Bold, bullet points, and paragraphs for structure
- Do NOT use ANSI escape codes, terminal formatting, or raw control characters

CRITICAL OUTPUT RULE: Because the output passes through a terminal renderer that strips
triple-backtick fences, you MUST use XML-style code block tags instead:
- Use <codeblock lang="python"> and </codeblock> instead of ```python and ```
- Use <code> and </code> instead of single backticks for inline code
- The post-processing script will convert these back to proper markdown
- Example:
  <codeblock lang="python">
  def example():
      return True
  </codeblock>

If no issues found:
```
## Code Review Results
✅ No issues found. The changes look good.
```

If files were omitted due to size, note them at the end:
```
**Note**: The following files were omitted due to size: {list}
```

**IMPORTANT**: The `{file_path}:{line_number}` format is parsed by the review posting script
to create inline PR comments. Ensure every comment has a valid file path (matching the diff's
`to_path`) and a line number visible in the diff's new side.
