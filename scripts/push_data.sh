#!/usr/bin/env bash
set -euo pipefail

for attempt in 1 2 3; do
  git pull --rebase origin "$GITHUB_REF_NAME"
  if git push origin "HEAD:refs/heads/$GITHUB_REF_NAME"; then
    exit 0
  fi
  if [ "$attempt" -lt 3 ]; then
    sleep "$attempt"
  fi
done
exit 1
