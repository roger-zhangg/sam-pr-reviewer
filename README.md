# SAM PR Reviewer

AI-powered code reviewer for GitHub pull requests, powered by [Kiro CLI](https://kiro.dev/cli/).

Automatically reviews PR diffs and posts inline comments with categorized findings covering security, bugs, error handling, performance, and more.

## Features

- **Inline PR comments** — findings posted directly on the relevant lines
- **5-pass review pipeline** — generate → deduplicate → confidence check → guideline compliance → refine
- **12 finding categories** — BUG, SECURITY, ERROR_HANDLING, INPUT_VALIDATION, PERFORMANCE, CONCURRENCY, RESOURCE_MANAGEMENT, NAMING, STYLE, DOCUMENTATION, TESTING, GENERAL
- **Cross-file context** — reads source files from the repo to verify findings (e.g., checking class hierarchies)
- **Configurable timeout** — partial results posted if the review exceeds the time limit
- **Auto-dismiss** — previous review comments are cleaned up before each new review
- **Custom guidelines** — bring your own coding guidelines to supplement the built-in ones
- **Custom rules** — add a `kiro-review.yaml` to your repo for project-specific review rules
- **Fork-safe** — uses `pull_request_target` to review PRs from forks without exposing secrets

## Quick Start

### 1. Get a Kiro API Key

[Sign in to Kiro](https://app.kiro.dev) and generate an API key from your account settings. Requires a Kiro Pro, Pro+, or Power subscription.

### 2. Add Secrets

In your GitHub repository, go to **Settings → Secrets and variables → Actions** and add:

| Secret | Description |
|---|---|
| `KIRO_API_KEY` | Your Kiro CLI API key |

The `GITHUB_TOKEN` is automatically available — no setup needed.

### 3. Create the Workflow

Add `.github/workflows/ai-code-review.yml` to your repository:

```yaml
name: AI Code Review

on:
  pull_request_target:
    types: [opened, synchronize, reopened]

permissions:
  contents: read
  pull-requests: write

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Fetch PR head
        run: git fetch origin "$PR_HEAD_SHA"
        env:
          PR_HEAD_SHA: ${{ github.event.pull_request.head.sha }}

      - uses: roger-zhangg/sam-pr-reviewer@v1
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          kiro_api_key: ${{ secrets.KIRO_API_KEY }}
```

Every PR will now get an AI code review.

**Why `pull_request_target`?** This trigger runs the workflow with the base repo's permissions, allowing the action to post review comments on PRs from forks. The workspace is checked out from the base branch (trusted), and only the git diff is used for review — fork code is never checked out onto disk.

## Inputs

| Input | Required | Default | Description |
|---|---|---|---|
| `github_token` | Yes | — | GitHub token for posting reviews |
| `kiro_api_key` | Yes | — | Kiro CLI API key for headless mode |
| `timeout_minutes` | No | `10` | Max review time in minutes. Partial results posted on timeout. |
| `guidelines_path` | No | — | Path to custom guidelines file (relative to repo root) |
| `dismiss_previous` | No | `true` | Delete previous SAM PR Reviewer comments before posting new review |

## Custom Guidelines

Provide your own coding guidelines to supplement the built-in ones:

```yaml
- uses: roger-zhangg/sam-pr-reviewer@v1
  with:
    github_token: ${{ secrets.GITHUB_TOKEN }}
    kiro_api_key: ${{ secrets.KIRO_API_KEY }}
    guidelines_path: docs/review-guidelines.md
```

Your guidelines file can be any markdown file with review criteria. It will be applied alongside the built-in guidelines.

## Custom Rules (`kiro-review.yaml`)

Add a `kiro-review.yaml` to your repository root for project-specific rules:

```yaml
custom-rules:
  - name: No console.log in production
    description: Remove console.log statements before merging
    file-patterns:
      - "src/**/*.ts"
      - "src/**/*.js"
    rule: Flag any console.log, console.warn, or console.error calls in production source files.

  - name: API error responses must include error codes
    file-patterns:
      - "src/api/**/*.ts"
    rule: All error responses from API handlers must include a machine-readable error code field.
```

## How It Works

1. **Checkout** — checks out the base branch (trusted) with full git history
2. **Fetch** — fetches the PR head commit for diffing (fork code is never checked out)
3. **Install** — installs Kiro CLI in headless mode using your API key
4. **Parse** — pre-generates structured diff JSON between base and head commits
5. **Review** — Kiro CLI (Claude Opus 4.6) runs a 5-pass review pipeline:
   - **Pass 1**: Generate initial comments from diff analysis
   - **Pass 2**: Deduplicate similar findings
   - **Pass 3**: Confidence check — read source files to verify, discard incorrect comments
   - **Pass 4**: Guideline compliance — verify against coding standards
   - **Pass 5**: Refine — polish comments with clear explanations and code examples
6. **Post** — findings posted as a PR review with inline comments on the relevant lines

## Security

This action is designed to run safely against untrusted PRs from forks.

| Concern | Mitigation |
|---|---|
| Fork code execution | Workspace is base branch only. Fork code is never on disk. Diffs are pre-parsed. |
| Shell injection | Agent has no shell access. Only read-only tools (read, grep, glob, code) are available. |
| Secret exfiltration | `KIRO_API_KEY` is unset before posting. Review text is sanitized for secret patterns before posting. |
| Prompt injection via PR content | Agent instructed to ignore config files from PR diff. No shell to exfiltrate data. |
| GitHub token scope | `pull-requests: write` only. Reviews posted as `COMMENT` (never `APPROVE` or `REQUEST_CHANGES`). |
| Expression injection | All GitHub context values passed via `env:` blocks, not inline `${{ }}` in `run:` steps. |

## Timeout Behavior

If the review exceeds `timeout_minutes`, the action posts whatever findings have been produced so far, with a note that the review was partial. If `KIRO_API_KEY` is not set, the action skips gracefully with a warning.

## License

MIT — see [LICENSE](LICENSE).
