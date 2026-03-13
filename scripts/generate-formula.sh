#!/usr/bin/env bash
# Generate a complete Homebrew formula for traceviz with all dependency resources.
# Run this AFTER publishing to PyPI.
#
# Usage:
#   ./scripts/generate-formula.sh <version> [output-file]
#   e.g. ./scripts/generate-formula.sh 0.1.0
#   e.g. ./scripts/generate-formula.sh 0.1.0 /tmp/traceviz.rb

set -euo pipefail

VERSION="${1:-}"
FORMULA_FILE="${2:-Formula/traceviz.rb}"
RETRY_ATTEMPTS="${TRACEVIZ_PYPI_RETRY_ATTEMPTS:-6}"
RETRY_DELAY_SECONDS="${TRACEVIZ_PYPI_RETRY_DELAY_SECONDS:-5}"
UV_BIN="${TRACEVIZ_UV_BIN:-uv}"
PYTHON_BIN="${TRACEVIZ_PYTHON_BIN:-python}"
if [ -z "$VERSION" ]; then
  echo "Usage: $0 <version> [output-file]"
  echo "Example: $0 0.1.0"
  exit 1
fi

echo "Generating Homebrew formula for traceviz==${VERSION}..."

mkdir -p "$(dirname "$FORMULA_FILE")"

VENV_DIR=$(mktemp -d)

cleanup() {
  rm -rf "$VENV_DIR"
}
trap cleanup EXIT

retry_with_backoff() {
  local attempts="$1"
  local delay="$2"
  local description="$3"
  shift 3

  local attempt=1
  while true; do
    if "$@"; then
      return 0
    fi

    if [ "$attempt" -ge "$attempts" ]; then
      echo "Failed to ${description} after ${attempts} attempts" >&2
      return 1
    fi

    echo "Attempt ${attempt}/${attempts} to ${description} failed; retrying in ${delay}s..." >&2
    attempt=$((attempt + 1))
    sleep "$delay"
  done
}

install_formula_dependencies() {
  "$UV_BIN" pip install --python "$VENV_DIR/bin/python3" --quiet "setuptools<81" homebrew-pypi-poet "traceviz==${VERSION}" >/dev/null
}

fetch_sdist_metadata() {
  "$PYTHON_BIN" - "$VERSION" <<'PY'
import json
import sys
import urllib.request

version = sys.argv[1]
with urllib.request.urlopen(f"https://pypi.org/pypi/traceviz/{version}/json") as response:
    data = json.load(response)

for artifact in data["urls"]:
    if artifact["packagetype"] == "sdist":
        print(artifact["url"], artifact["digests"]["sha256"])
        break
else:
    raise SystemExit(f"No sdist found for traceviz {version}")
PY
}

"$UV_BIN" venv "$VENV_DIR" >/dev/null
retry_with_backoff \
  "$RETRY_ATTEMPTS" \
  "$RETRY_DELAY_SECONDS" \
  "install traceviz==${VERSION} into the formula generator environment" \
  install_formula_dependencies

# Generate dependency resource blocks. `poet` also emits the main package as a
# resource; drop that block because the formula installs it via `url`.
RAW_RESOURCES=$(PYTHONWARNINGS=ignore "$VENV_DIR/bin/poet" traceviz)
RESOURCES=$(printf '%s\n' "$RAW_RESOURCES" | awk '
  /^  resource "traceviz" do$/ {skip=1; next}
  skip && /^  end$/ {skip=0; next}
  !skip {print}
')

# Read sdist metadata directly from the versioned PyPI JSON endpoint.
SDIST_METADATA=$(
  retry_with_backoff \
    "$RETRY_ATTEMPTS" \
    "$RETRY_DELAY_SECONDS" \
    "fetch sdist metadata for traceviz==${VERSION}" \
    fetch_sdist_metadata
)
read -r SDIST_URL SHA256 <<< "$SDIST_METADATA"

cat > "$FORMULA_FILE" << RUBY
class Traceviz < Formula
  include Language::Python::Virtualenv

  desc "Traceroute visualization on a world map"
  homepage "https://github.com/shixy96/traceviz"
  url "${SDIST_URL}"
  sha256 "${SHA256}"
  license "MIT"

  depends_on "python@3.13"

${RESOURCES}

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "traceviz", shell_output("#{bin}/traceviz --help")
  end
end
RUBY

echo "Formula written to ${FORMULA_FILE}"
echo ""
echo "Next steps:"
echo "  1. Review the generated formula"
echo "  2. Commit it to shixy96/homebrew-tap"
echo "  3. Install with: brew install shixy96/tap/traceviz"
