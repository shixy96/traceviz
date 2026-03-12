#!/usr/bin/env bash
# Generate a complete Homebrew formula for traceviz with all dependency resources.
# Run this AFTER publishing to PyPI.
#
# Usage:
#   ./scripts/generate-formula.sh [version]
#   e.g. ./scripts/generate-formula.sh 0.1.0

set -euo pipefail

VERSION="${1:-}"
if [ -z "$VERSION" ]; then
  echo "Usage: $0 <version>"
  echo "Example: $0 0.1.0"
  exit 1
fi

# Ensure poet is installed
if ! command -v poet &> /dev/null; then
  echo "Installing homebrew-pypi-poet..."
  pip install homebrew-pypi-poet
fi

echo "Generating Homebrew formula for traceviz==${VERSION}..."

FORMULA_FILE="Formula/traceviz.rb"
mkdir -p "$(dirname "$FORMULA_FILE")"

# Generate resource blocks
RESOURCES=$(poet traceviz=="${VERSION}")

# Download sdist and compute sha256
TMPDIR=$(mktemp -d)
pip download --no-deps --no-binary :all: -d "$TMPDIR" "traceviz==${VERSION}" 2>/dev/null
SDIST=$(ls "$TMPDIR"/traceviz-*.tar.gz 2>/dev/null | head -1)
if [ -n "$SDIST" ]; then
  SHA256=$(shasum -a 256 "$SDIST" | cut -d' ' -f1)
else
  SHA256="TODO"
fi
rm -rf "$TMPDIR"

cat > "$FORMULA_FILE" << RUBY
class Traceviz < Formula
  include Language::Python::Virtualenv

  desc "Traceroute visualization on a world map"
  homepage "https://github.com/shixy96/traceviz"
  url "https://files.pythonhosted.org/packages/source/t/traceviz/traceviz-${VERSION}.tar.gz"
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
echo "  2. Copy to your homebrew-tap repo: shixy96/homebrew-tap"
echo "  3. Push to make it available via: brew install shixy96/tap/traceviz"
