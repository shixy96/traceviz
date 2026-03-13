# Repository Guidelines

## Project Structure & Module Organization
`traceviz/` contains the application code: `cli.py` is the entry point, `tracer.py` runs and parses traceroute output, `ip_lookup.py` handles IP metadata, `analyzer.py` classifies hops, and `server.py` serves the Flask UI. Frontend assets live in `traceviz/static/`. `tests/` mirrors the package with pytest suites such as `tests/test_cli.py` and `tests/test_server.py`. Utility automation lives in `scripts/`, including `scripts/generate-formula.sh`, which writes Homebrew output under `Formula/`.

## Build, Test, and Development Commands
- `uv sync --extra dev`: install runtime and developer dependencies for Python 3.12+.
- `uv run pytest --cov --cov-report=term-missing`: run the full test suite with coverage for `traceviz`.
- `uv run ruff check traceviz/ tests/`: run lint and import-order checks.
- `uv run ruff format traceviz/ tests/`: apply the repository formatter.
- `uv run python -m traceviz --demo example.com`: smoke-test the CLI and local UI without running a real traceroute.

## Coding Style & Naming Conventions
Use 4-space indentation, LF line endings, and UTF-8 text; `.editorconfig` defines the defaults. Ruff formatting is authoritative: prefer double quotes and keep lines within the configured 120-character limit unless an existing file already documents an exception. Use `snake_case` for modules and functions, `UPPER_SNAKE_CASE` for constants, and explicit argument names for CLI-facing behavior. Keep functions small and behavior direct.

## Testing Guidelines
Use pytest for all coverage. Name files `test_<module>.py` and test functions `test_<behavior>`, for example `test_main_parses_demo_argument`. Add regression tests for any CLI flag, traceroute parsing rule, IP lookup fallback, or Flask response that changes. Run `uv run pytest --cov --cov-report=term-missing` before opening a PR.

## Commit & Pull Request Guidelines
Use Conventional Commits for all commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `ci:`, and similar types. Keep subjects imperative and focused, for example `feat: add JSON-only CLI mode` or `fix: handle empty traceroute output`. Avoid mixing refactors with behavior changes in the same commit. PR titles must also follow Conventional Commits because squash merges use the PR title as the final commit subject on `main`; PR descriptions become the squash commit body. PRs should summarize the change, link related issues, list the verification commands you ran, and include screenshots or sample CLI/JSON output when `traceviz/static/` or other user-visible behavior changes. Update `README.md` for user-facing changes. Do not hand-edit `CHANGELOG.md`; generate it from `main` with `./scripts/tag-release.sh`.
