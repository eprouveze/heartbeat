#!/usr/bin/env bash
# orphan-audit.sh — durability catch-all for the heartbeat loop.
#
# A heartbeat session can die (machine reboot, context loss, crash) after creating
# a durable file but before committing it. That work is then lost on the next pull.
# This audit finds untracked durable files left in the repo so the next tick can
# commit them (a valid tick action) instead of letting them rot.
#
# Read-only. Exit 0 = clean. Exit 1 = orphans found (listed on stdout).
#
# Usage:
#   bin/orphan-audit.sh [repo-root]
#
# What counts as "durable" is intentionally narrow: tracked-looking documentation
# and source left untracked. Volatile heartbeat state (board/ledger/tick log) and
# the usual noise (node_modules, build output, dotfiles) are excluded so the audit
# stays quiet unless there is genuinely orphaned work.
set -euo pipefail

REPO="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
cd "$REPO"

# Glob of paths that are NEVER orphans (volatile state + noise). Extend per deployment.
EXCLUDE_RE='(^|/)(node_modules|\.venv|venv|dist|build|\.next|target|__pycache__)/|(^|/)\.heartbeat/|(board|ledger|ticks)\.(html|jsonl)$|\.(log|tmp|lock)$|(^|/)\.DS_Store$'

# Durable = untracked files whose extension suggests real work (docs, code, config).
DURABLE_RE='\.(md|markdown|txt|py|js|ts|tsx|jsx|sh|json|ya?ml|toml|sql|html|css)$'

# Portable collect (no `mapfile` — macOS ships bash 3.2 where it doesn't exist).
orphans=()
while IFS= read -r line; do
  [ -n "$line" ] && orphans+=("$line")
done < <(
  git ls-files --others --exclude-standard \
    | grep -E "$DURABLE_RE" \
    | grep -vE "$EXCLUDE_RE" \
    || true
)

if [ "${#orphans[@]}" -eq 0 ]; then
  echo "orphan-audit: clean (no untracked durable files)"
  exit 0
fi

echo "orphan-audit: ${#orphans[@]} untracked durable file(s) — commit by path next tick:"
for f in "${orphans[@]}"; do
  echo "  $f"
done
exit 1
