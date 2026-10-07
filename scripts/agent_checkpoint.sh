#!/usr/bin/env bash
# Commit and push the current work so another session can resume from it.
#
# Usage: scripts/agent_checkpoint.sh <issue-number> "<what just changed>"
#
# Update .agent/progress/issue-<n>.md first (round log, state for the next
# session). This script refuses to run on main and commits everything in the
# working tree, so check `git status` for stray files before calling it.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
issue="${1:-}"
message="${2:-}"
if ! [[ "$issue" =~ ^[0-9]+$ ]] || [ -z "$message" ]; then
  echo "usage: $0 <issue-number> \"<message>\"" >&2
  exit 2
fi

cd "$root"
branch="$(git rev-parse --abbrev-ref HEAD)"
case "$branch" in
  main|master|HEAD) echo "refusing to checkpoint on '$branch'; use an issue branch" >&2; exit 1 ;;
esac
if [ ! -f ".agent/progress/issue-$issue.md" ]; then
  echo "missing .agent/progress/issue-$issue.md: create it from .agent/progress/TEMPLATE.md first" >&2
  exit 1
fi

python3 -I scripts/check_agent_progress.py
git add -A
if git diff --cached --quiet; then
  echo "nothing new to checkpoint"
else
  git commit -q -m "wip(#$issue): $message"
  echo "committed: wip(#$issue): $message"
fi
git push -q -u origin "$branch"
echo "pushed $branch"
