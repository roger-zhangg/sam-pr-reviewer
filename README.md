# SAM PR Reviewer

AI-powered code reviewer for GitHub pull requests, powered by [Kiro CLI](https://kiro.dev/cli/).

Automatically reviews PR diffs and posts inline comments with categorized findings covering security, bugs, error handling, performance, and more.

## Features

- **Inline PR comments** — findings are posted directly on the relevant lines in your PR
- **5-pass review pipeline** — generate → deduplicate → confidence check → guideline compliance → refine
- **12 finding categories** — BUG, SECURITY, ERROR_HANDLING, INPUT_VALIDATION, PERFORMANCE, CONCURRENCY, RESOURCE_MANAGEMENT, NAMING, STYLE, DOCUMENTATION, TESTING, GENERAL
- **Configurable timeout** — partial results are posted if the review exceeds the time limit
- **Custom guidelines** — bring your own coding guidelines to supplement the built-in ones
- **Custom rules** — add a `kiro-review.yaml` to your repo for project-specific review rules

## Quick Start

### 1. Get a Kiro API Key

[Sign in to Kiro](https://app.kiro.dev) and generate an API key from your account settings.

### 2. Add Secrets

In your GitHub repository, go to **Settings → Secrets and variables → Actions** and add:

| Secret | Description |
|---|---|
| `KIRO_API_KEY` | Your Kiro CLI API key |

The `GITHUB_TOKEN` is automatically available — no setup needed.

### 3. Create the Workflow

Add `.github/workflows/sam-pr-reviewer.yml` to your repository:

```yaml
name: SAM PR Review

on:
  pull_request:
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

      - uses: roger-zhangg/sam-pr-reviewer@v1
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          kiro_api_key: ${{ secrets.KIRO_API_KEY }}
```

That's it. Every PR will now get an AI code review.

## Inputs

| Input | Required | Default | Description |
|---|---|---|---|
| `github_token` | Yes | — | GitHub token for posting reviews |
| `kiro_api_key` | Yes | — | Kiro CLI API key for headless mode |
| `timeout_minutes` | No | `10` | Max review time in minutes. Partial results posted on timeout. |
| `guidelines_path` | No | — | Path to custom guidelines file (relative to repo root) |

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

1. **Checkout** — the action checks out your PR with full git history
2. **Install** — installs Kiro CLI in headless mode using your API key
3. **Parse** — extracts structured diff data between the PR base and head commits
4. **Review** — Kiro CLI runs a 5-pass review pipeline:
   - **Pass 1**: Generate initial comments from diff analysis
   - **Pass 2**: Deduplicate similar findings
   - **Pass 3**: Confidence check — discard speculative or incorrect comments
   - **Pass 4**: Guideline compliance — verify against coding standards
   - **Pass 5**: Refine — polish comments with clear explanations and code examples
5. **Post** — findings are posted as a PR review with inline comments on the relevant lines

## Timeout Behavior

If the review exceeds `timeout_minutes`, the action posts whatever findings have been produced so far, with a note that the review was partial. This ensures you always get feedback, even on large PRs.

## Security

- The action treats all PR code as **untrusted** — it only reads and analyzes code, never executes it
- Reviews are posted as `COMMENT` (never `APPROVE` or `REQUEST_CHANGES`) — the AI won't block your merges
- Your Kiro API key is passed via GitHub secrets and never exposed in logs

## License

MIT — see [LICENSE](LICENSE).
