#!/usr/bin/env bash
# Heartbeat launcher — igniting the autonomous loop on this machine.
#
# Usage: heartbeat-launch.sh [working-directory]
#   working-directory: where the heartbeat session runs (default: $HOME).
#
# The loop is an INTERACTIVE terminal session by design (subscription-side
# billing; the owner can interrupt at any moment). Stop it any time with:
#   touch ~/.heartbeat-stop
#
# PERMISSION MODE: this launcher uses `--permission-mode auto` — safe actions
# auto-approve; the permission classifier still hard-blocks risky ones. On a
# machine where you want every action manually approved (e.g. an employer's
# machine with strict IT policy), launch with HEARTBEAT_MANUAL=1 to drop the flag.
set -euo pipefail

WORK_DIR="${1:-$HOME}"
STATE_DIR="$HOME/.heartbeat"
KIT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ -f "$HOME/.heartbeat-stop" ]; then
    echo "Kill switch present at ~/.heartbeat-stop — remove it first:"
    echo "  rm ~/.heartbeat-stop"
    exit 1
fi

# Pre-flight: the /heartbeat-kit skill must actually be deployed where the claude
# CLI loads skills from, or the loop prompt degrades to plain text.
# (Named heartbeat-kit, not heartbeat, so it never collides with a project-specific
# /heartbeat skill you may already have.)
if [ ! -f "$HOME/.claude/skills/heartbeat-kit/SKILL.md" ]; then
    echo "ERROR: ~/.claude/skills/heartbeat-kit/SKILL.md not found." >&2
    echo "Deploy the kit's skill first, e.g.:" >&2
    echo "  mkdir -p ~/.claude/skills/heartbeat-kit" >&2
    echo "  cp \"$KIT_ROOT/skills/heartbeat-kit/SKILL.md\" ~/.claude/skills/heartbeat-kit/" >&2
    exit 1
fi

# First-ignite state setup. State lives OUTSIDE ~/.claude on purpose: dotfile
# syncs of this repo must never clobber or pick up heartbeat state.
mkdir -p "$STATE_DIR"
if [ ! -f "$STATE_DIR/board.html" ]; then
    cp "$KIT_ROOT/templates/heartbeat-board.html" "$STATE_DIR/board.html"
    echo "Initialized board: $STATE_DIR/board.html"
fi
touch "$STATE_DIR/ledger.jsonl" "$STATE_DIR/ticks.jsonl"

CLAUDE_BIN="$(command -v claude || true)"
if [ -z "$CLAUDE_BIN" ]; then
    echo "claude CLI not found on PATH" >&2
    exit 1
fi

echo "── Heartbeat igniting ──"
echo "  work dir : $WORK_DIR"
echo "  state    : $STATE_DIR"
echo "  stop with: touch ~/.heartbeat-stop"
echo

cd "$WORK_DIR"
# The positional argument is the session's initial input: `/loop /heartbeat-kit` tells
# the `loop` skill to re-run `/heartbeat-kit` on a self-paced schedule. This relies on the
# claude CLI treating a leading positional arg as the opening prompt/command (tested with
# current Claude Code). If your CLI version differs, run `claude` and type it manually.
if [ "${HEARTBEAT_MANUAL:-0}" = "1" ]; then
    exec "$CLAUDE_BIN" "/loop /heartbeat-kit"
else
    exec "$CLAUDE_BIN" --permission-mode auto "/loop /heartbeat-kit"
fi
