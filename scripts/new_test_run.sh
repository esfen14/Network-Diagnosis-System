#!/usr/bin/env bash
# Create docs/test-runs/<date>-<slug>/REPORT.md from the template.
#
# Usage: scripts/new_test_run.sh <slug> [path/to/test-plan.md]
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
slug="${1:-}"
plan="${2:-none}"

if [ -z "$slug" ] || ! [[ "$slug" =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
  echo "usage: $0 <slug: lowercase letters, digits, hyphens> [plan path]" >&2
  exit 2
fi

date_part="$(date +%F)"
commit="$(git -C "$root" rev-parse --short HEAD)"
dir="$root/docs/test-runs/$date_part-$slug"

if [ -e "$dir" ]; then
  echo "already exists: $dir" >&2
  exit 1
fi
if ! git -C "$root" diff --quiet || ! git -C "$root" diff --cached --quiet; then
  echo "warning: working tree has uncommitted changes; the commit below is not what you are testing" >&2
fi

mkdir -p "$dir"
sed -e "s|{{SLUG}}|$slug|g" -e "s|{{DATE}}|$date_part|g" -e "s|{{COMMIT}}|$commit|g" -e "s|{{PLAN}}|$plan|g" \
  "$root/docs/test-runs/TEMPLATE.md" > "$dir/REPORT.md"
echo "created ${dir#"$root"/}/REPORT.md"
