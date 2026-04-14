#!/usr/bin/env bash
set -euo pipefail

# --- Inputs (set by composite action step env) ---
TIMEOUT_MINUTES="${INPUT_TIMEOUT_MINUTES:-10}"
GUIDELINES_PATH="${INPUT_GUIDELINES_PATH:-}"

# --- Derived from GitHub context ---
PR_NUMBER=$(jq -r '.pull_request.number' "$GITHUB_EVENT_PATH")
REPO_FULL="${GITHUB_REPOSITORY}"
BASE_SHA=$(jq -r '.pull_request.base.sha' "$GITHUB_EVENT_PATH")
HEAD_SHA=$(jq -r '.pull_request.head.sha' "$GITHUB_EVENT_PATH")

# --- Validate inputs ---
if ! [[ "$PR_NUMBER" =~ ^[0-9]+$ ]]; then
  echo "::error::Invalid PR number: ${PR_NUMBER}"
  exit 1
fi
if ! [[ "$BASE_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "::error::Invalid base SHA"
  exit 1
fi
if ! [[ "$HEAD_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "::error::Invalid head SHA"
  exit 1
fi

echo "Reviewing PR #${PR_NUMBER} on ${REPO_FULL}"
echo "Diff: ${BASE_SHA}..${HEAD_SHA}"

# --- Install Kiro CLI with integrity check ---
echo "Installing Kiro CLI..."
KIRO_INSTALL_SCRIPT=$(mktemp)
curl -fsSL https://cli.kiro.dev/install -o "$KIRO_INSTALL_SCRIPT"
# TODO: pin checksum once a stable release is available
# echo "EXPECTED_SHA256  $KIRO_INSTALL_SCRIPT" | sha256sum -c -
bash "$KIRO_INSTALL_SCRIPT"
rm -f "$KIRO_INSTALL_SCRIPT"
export PATH="$HOME/.local/bin:$PATH"

# --- Prepare the review prompt (written to file, not shell variable) ---
ACTION_DIR="${GITHUB_ACTION_PATH}"
SKILL_DIR="${ACTION_DIR}"
PROMPT_FILE=$(mktemp)

cat > "$PROMPT_FILE" <<PROMPT_EOF
Review the pull request changes in this repository.

Use the diff parser to get structured diff data:
  python3 ${SKILL_DIR}/scripts/parse_diff.py --from ${BASE_SHA} --to ${HEAD_SHA}

For large diffs, use --summary first, then --file for each file:
  python3 ${SKILL_DIR}/scripts/parse_diff.py --summary --from ${BASE_SHA} --to ${HEAD_SHA}
  python3 ${SKILL_DIR}/scripts/parse_diff.py --file <path> --from ${BASE_SHA} --to ${HEAD_SHA}

Follow the review pipeline in the agent instructions. Output your review in the exact format specified.
PROMPT_EOF

# --- Append custom guidelines (with path traversal guard) ---
if [ -n "$GUIDELINES_PATH" ]; then
  RESOLVED_PATH=$(realpath -m "$GUIDELINES_PATH" 2>/dev/null || true)
  WORKSPACE=$(realpath "$GITHUB_WORKSPACE")
  if [[ "$RESOLVED_PATH" != "$WORKSPACE"/* ]]; then
    echo "::error::guidelines_path must be within the repository: ${GUIDELINES_PATH}"
    exit 1
  fi
  if [ -f "$RESOLVED_PATH" ]; then
    cat >> "$PROMPT_FILE" <<GUIDE_EOF

Custom guidelines file is at: ${RESOLVED_PATH}
Read it and apply those rules in addition to the built-in guidelines.
GUIDE_EOF
  fi
fi

# --- Run Kiro CLI with timeout (stderr separated) ---
echo "Running code review (timeout: ${TIMEOUT_MINUTES}m)..."
REVIEW_OUTPUT_FILE=$(mktemp)
KIRO_STDERR_LOG=$(mktemp)
TIMEOUT_SECONDS=$((TIMEOUT_MINUTES * 60))

set +e
timeout "${TIMEOUT_SECONDS}" kiro-cli chat \
  --no-interactive \
  --agent "${SKILL_DIR}/.kiro/agents/code-reviewer.json" \
  --prompt-file "$PROMPT_FILE" \
  > "$REVIEW_OUTPUT_FILE" 2>"$KIRO_STDERR_LOG"
EXIT_CODE=$?
set -e

if [ $EXIT_CODE -eq 124 ]; then
  echo "::warning::Review timed out after ${TIMEOUT_MINUTES} minutes. Posting partial results."
  echo -e "\n\n---\n⚠️ **Review timed out** after ${TIMEOUT_MINUTES} minutes. The above findings are partial." >> "$REVIEW_OUTPUT_FILE"
elif [ $EXIT_CODE -ne 0 ]; then
  echo "::warning::Kiro CLI exited with code ${EXIT_CODE}. Check logs."
fi

# Log stderr to CI (not to review output) for debugging
if [ -s "$KIRO_STDERR_LOG" ]; then
  echo "::group::Kiro CLI stderr"
  cat "$KIRO_STDERR_LOG"
  echo "::endgroup::"
fi

# --- Post review to GitHub PR ---
echo "Posting review to PR #${PR_NUMBER}..."
export GITHUB_TOKEN
python3 "${SKILL_DIR}/scripts/post_review.py" \
  --repo "$REPO_FULL" \
  --pr "$PR_NUMBER" \
  --commit "$HEAD_SHA" \
  --review-file "$REVIEW_OUTPUT_FILE"

rm -f "$REVIEW_OUTPUT_FILE" "$PROMPT_FILE" "$KIRO_STDERR_LOG"
echo "Done."
