"""Tests for the Homebrew formula generator script."""

import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate-formula.sh"
pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Homebrew formula generation is only exercised on POSIX runners",
)


def _write_executable(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    path.chmod(0o755)


def _bash_path(path: Path) -> str:
    return path.as_posix()


def _write_fake_uv(path: Path) -> None:
    _write_executable(
        path,
        """#!/usr/bin/env bash
set -euo pipefail

if [ -n "${TRACEVIZ_FAKE_UV_LOG_FILE:-}" ]; then
  printf '%s\\n' "$*" >> "$TRACEVIZ_FAKE_UV_LOG_FILE"
fi

if [ "$1" = "venv" ]; then
  mkdir -p "$2/bin"
  : > "$2/bin/python3"
  chmod +x "$2/bin/python3"
  exit 0
fi

if [ "$1" = "pip" ]; then
  shift
  PYTHON_PATH=""
  PACKAGE_SPEC=""
  while [ "$#" -gt 0 ]; do
    if [ "$1" = "--python" ]; then
      PYTHON_PATH="$2"
      shift 2
      continue
    fi
    PACKAGE_SPEC="$1"
    shift
  done

  if [ -z "$PYTHON_PATH" ]; then
    echo "missing --python argument" >&2
    exit 1
  fi

  if [ -n "${TRACEVIZ_FAKE_UV_FAIL_PACKAGE_PATTERN:-}" ]; then
    case "$PACKAGE_SPEC" in
      *"${TRACEVIZ_FAKE_UV_FAIL_PACKAGE_PATTERN}"*)
        echo "simulated install failure for $PACKAGE_SPEC" >&2
        exit 1
        ;;
    esac
  fi

  POET_PATH="$(dirname "$PYTHON_PATH")/poet"
  cat > "$POET_PATH" <<'EOF'
#!/usr/bin/env bash
cat <<'OUT'
  resource "traceviz" do
    url "https://example.invalid/traceviz-resource.tar.gz"
    sha256 "0000000000000000000000000000000000000000000000000000000000000000"
  end
  resource "requests" do
    url "https://example.invalid/requests.tar.gz"
    sha256 "1111111111111111111111111111111111111111111111111111111111111111"
  end
  resource "urllib3" do
    url "https://example.invalid/urllib3.tar.gz"
    sha256 "2222222222222222222222222222222222222222222222222222222222222222"
  end
OUT
EOF
  chmod +x "$POET_PATH"
  exit 0
fi

echo "unexpected uv invocation: $*" >&2
exit 1
""",
    )


def _write_fake_metadata_script(path: Path, *lines: str) -> None:
    quoted_lines = ", ".join(repr(line) for line in lines)
    _write_executable(
        path,
        f"""#!/usr/bin/env bash
python - <<'PY'
lines = [{quoted_lines}]
for line in lines:
    print(line)
PY
""",
    )


def test_generate_formula_script_writes_expected_formula(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()

    _write_fake_uv(fake_bin / "uv")
    uv_log = tmp_path / "uv.log"
    _write_fake_metadata_script(
        fake_bin / "python",
        "https://files.pythonhosted.org/packages/py3/traceviz/traceviz-1.2.3-py3-none-any.whl",
        "https://files.pythonhosted.org/packages/source/t/traceviz/traceviz-1.2.3.tar.gz",
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )

    output = tmp_path / "generated" / "Formula" / "traceviz.rb"
    env = os.environ.copy()
    env["TRACEVIZ_UV_BIN"] = _bash_path(fake_bin / "uv")
    env["TRACEVIZ_PYTHON_BIN"] = _bash_path(fake_bin / "python")
    env["TRACEVIZ_FAKE_UV_LOG_FILE"] = _bash_path(uv_log)

    result = subprocess.run(
        ["bash", _bash_path(SCRIPT), "1.2.3", _bash_path(output)],
        capture_output=True,
        check=False,
        cwd=ROOT,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert output.is_file()
    formula = output.read_text(encoding="utf-8")
    assert "class Traceviz < Formula" in formula
    assert 'url "https://files.pythonhosted.org/packages/source/t/traceviz/traceviz-1.2.3.tar.gz"' in formula
    assert 'sha256 "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"' in formula
    assert 'resource "requests" do' in formula
    assert 'resource "urllib3" do' in formula
    assert 'resource "traceviz" do' not in formula
    assert "virtualenv_install_with_resources" in formula
    assert f"Formula written to {output}" in result.stdout
    uv_commands = uv_log.read_text(encoding="utf-8")
    assert "traceviz==1.2.3" not in uv_commands
    assert "traceviz-1.2.3-py3-none-any.whl" in uv_commands


def test_generate_formula_script_retries_release_metadata_lookup(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()

    _write_fake_uv(fake_bin / "uv")
    attempt_file = tmp_path / "python-attempts.txt"
    _write_executable(
        fake_bin / "python",
        f"""#!/usr/bin/env bash
set -euo pipefail

ATTEMPT_FILE={shlex.quote(_bash_path(attempt_file))}
ATTEMPTS=0
if [ -f "$ATTEMPT_FILE" ]; then
  ATTEMPTS=$(cat "$ATTEMPT_FILE")
fi
ATTEMPTS=$((ATTEMPTS + 1))
printf '%s' "$ATTEMPTS" > "$ATTEMPT_FILE"

if [ "$ATTEMPTS" -eq 1 ]; then
  echo "temporary PyPI metadata failure" >&2
  exit 1
fi

python - <<'PY'
print("https://files.pythonhosted.org/packages/py3/traceviz/traceviz-1.2.3-py3-none-any.whl")
print("https://files.pythonhosted.org/packages/source/t/traceviz/traceviz-1.2.3.tar.gz")
print("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
PY
""",
    )

    output = tmp_path / "generated" / "Formula" / "traceviz.rb"
    env = os.environ.copy()
    env["TRACEVIZ_UV_BIN"] = _bash_path(fake_bin / "uv")
    env["TRACEVIZ_PYTHON_BIN"] = _bash_path(fake_bin / "python")
    env["TRACEVIZ_PYPI_RETRY_ATTEMPTS"] = "2"
    env["TRACEVIZ_PYPI_RETRY_DELAY_SECONDS"] = "0"

    result = subprocess.run(
        ["bash", _bash_path(SCRIPT), "1.2.3", _bash_path(output)],
        capture_output=True,
        check=False,
        cwd=ROOT,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert output.is_file()
    assert attempt_file.read_text(encoding="utf-8") == "2"
    assert "Attempt 1/2 to fetch release metadata for traceviz==1.2.3 failed" in result.stderr


def test_generate_formula_script_falls_back_to_sdist_when_wheel_is_missing(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()

    _write_fake_uv(fake_bin / "uv")
    uv_log = tmp_path / "uv.log"
    _write_fake_metadata_script(
        fake_bin / "python",
        "",
        "https://files.pythonhosted.org/packages/source/t/traceviz/traceviz-1.2.3.tar.gz",
        "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
    )

    output = tmp_path / "generated" / "Formula" / "traceviz.rb"
    env = os.environ.copy()
    env["TRACEVIZ_UV_BIN"] = _bash_path(fake_bin / "uv")
    env["TRACEVIZ_PYTHON_BIN"] = _bash_path(fake_bin / "python")
    env["TRACEVIZ_FAKE_UV_LOG_FILE"] = _bash_path(uv_log)

    result = subprocess.run(
        ["bash", _bash_path(SCRIPT), "1.2.3", _bash_path(output)],
        capture_output=True,
        check=False,
        cwd=ROOT,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    formula = output.read_text(encoding="utf-8")
    assert 'url "https://files.pythonhosted.org/packages/source/t/traceviz/traceviz-1.2.3.tar.gz"' in formula
    assert 'sha256 "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"' in formula
    uv_commands = uv_log.read_text(encoding="utf-8")
    assert "traceviz-1.2.3-py3-none-any.whl" not in uv_commands
    assert "traceviz-1.2.3.tar.gz" in uv_commands


def test_generate_formula_script_falls_back_to_sdist_when_wheel_download_fails(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()

    _write_fake_uv(fake_bin / "uv")
    uv_log = tmp_path / "uv.log"
    wheel_url = "https://files.pythonhosted.org/packages/py3/traceviz/traceviz-1.2.3-py3-none-any.whl"
    sdist_url = "https://files.pythonhosted.org/packages/source/t/traceviz/traceviz-1.2.3.tar.gz"
    _write_fake_metadata_script(
        fake_bin / "python",
        wheel_url,
        sdist_url,
        "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
    )

    output = tmp_path / "generated" / "Formula" / "traceviz.rb"
    env = os.environ.copy()
    env["TRACEVIZ_UV_BIN"] = _bash_path(fake_bin / "uv")
    env["TRACEVIZ_PYTHON_BIN"] = _bash_path(fake_bin / "python")
    env["TRACEVIZ_FAKE_UV_LOG_FILE"] = _bash_path(uv_log)
    env["TRACEVIZ_FAKE_UV_FAIL_PACKAGE_PATTERN"] = "traceviz-1.2.3-py3-none-any.whl"

    result = subprocess.run(
        ["bash", _bash_path(SCRIPT), "1.2.3", _bash_path(output)],
        capture_output=True,
        check=False,
        cwd=ROOT,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "falling back to" in result.stderr
    formula = output.read_text(encoding="utf-8")
    assert f'url "{sdist_url}"' in formula
    assert 'sha256 "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"' in formula
    uv_commands = uv_log.read_text(encoding="utf-8")
    assert "traceviz-1.2.3-py3-none-any.whl" in uv_commands
    assert "traceviz-1.2.3.tar.gz" in uv_commands
