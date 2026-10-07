#!/usr/bin/env bash
# Give an agent its own checkout, so two agents (or an agent and you) never share a
# working tree, branch or uncommitted files.
#
# Usage: scripts/agent-worktree.sh <name> [--no-install]
#
# Creates ../<repo folder>-<name> as a git worktree on a new branch qa/<name> from
# origin/main, with its own Python environment (server/.venv) and Node modules
# (client/node_modules), which are per-checkout and git-ignored. Start the agent from
# that folder. Remove it later with: git worktree remove ../<repo folder>-<name>
set -euo pipefail

name="${1:-}"
install=1
[ "${2:-}" = "--no-install" ] && install=0
if ! [[ "$name" =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
  echo "usage: $0 <name: lowercase letters, digits, hyphens> [--no-install]" >&2
  exit 2
fi

root="$(git rev-parse --show-toplevel)"
target="$(dirname "$root")/$(basename "$root")-$name"
branch="qa/$name"

if [ -e "$target" ]; then
  echo "already exists: $target" >&2
  exit 1
fi
if git -C "$root" show-ref --verify --quiet "refs/heads/$branch"; then
  echo "branch $branch already exists; pick another name or delete the branch first" >&2
  exit 1
fi

git -C "$root" fetch -q origin
git -C "$root" worktree add -q -b "$branch" "$target" origin/main
echo "created $target on branch $branch"

if [ "$install" = 1 ]; then
  cd "$target"
  if command -v uv >/dev/null; then
    uv venv --python 3.14 server/.venv
    uv pip install --python server/.venv/bin/python -r server/requirements.txt -r server/requirements-test.txt
  else
    python3.14 -m venv server/.venv
    server/.venv/bin/python -m pip install -r server/requirements.txt -r server/requirements-test.txt
  fi
  (cd client && npm ci)
fi

echo
echo "Start your agent from: $target"
echo "It creates its own issue branches from origin/main (see .agent/workflows/work-issue.md)."
