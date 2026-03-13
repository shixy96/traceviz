#!/usr/bin/env bash

set -euo pipefail

REMOTE="${1:-origin}"
BRANCH="$(git branch --show-current)"
CLIFF_BIN="${GIT_CLIFF_BIN:-git-cliff}"

if [ "$BRANCH" != "main" ]; then
  echo "Release tags must be created from the main branch (current: ${BRANCH})." >&2
  exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
  echo "Working tree is not clean. Commit or stash changes before tagging." >&2
  exit 1
fi

if ! command -v "$CLIFF_BIN" >/dev/null 2>&1; then
  echo "git-cliff is required to generate CHANGELOG.md before tagging." >&2
  echo "Install git-cliff and retry, or set GIT_CLIFF_BIN to the executable path." >&2
  exit 1
fi

VERSION="$(
  uv run python - <<'PY'
from traceviz import __version__

print(__version__)
PY
)"
TAG="v${VERSION}"

if git rev-parse -q --verify "refs/tags/${TAG}" >/dev/null 2>&1; then
  echo "Tag ${TAG} already exists." >&2
  exit 1
fi

echo "Generating CHANGELOG.md for ${TAG}..."
"$CLIFF_BIN" --config .git-cliff.toml --tag "${TAG}" --prepend CHANGELOG.md

if git diff --quiet -- CHANGELOG.md; then
  echo "No unreleased changelog entries were generated. Refusing to create ${TAG}." >&2
  exit 1
fi

git add CHANGELOG.md
git commit -m "chore(release): ${TAG}"

echo "Creating and pushing ${TAG} to ${REMOTE}..."
git tag -a "${TAG}" -m "Release ${TAG}"
git push "${REMOTE}" "${BRANCH}"
git push "${REMOTE}" "${TAG}"
