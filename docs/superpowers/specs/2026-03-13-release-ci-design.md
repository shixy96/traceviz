# Release And CI Workflow Design

## Goals

- Keep cross-platform tests in CI.
- Enforce a minimum test coverage of 95% in one stable environment.
- Split release publishing from Homebrew publishing so Homebrew failures do not block the core release path.

## CI Design

- Keep the existing matrix test job on macOS, Linux, and Windows for Python 3.12 and 3.13.
- Add a dedicated `coverage` job on `ubuntu-latest` with Python 3.12.
- Enforce coverage with `pytest --cov --cov-report=term-missing --cov-fail-under=95`.
- Keep PR title validation unchanged.

## Release Design

- Keep the tag-triggered release workflow.
- Use a `publish` job for package build, PyPI publish, and GitHub Release creation.
- Move Homebrew work into a separate `homebrew` job that depends on `publish`.
- Run Homebrew token validation, tap checkout, formula generation, and tap push only in the `homebrew` job.
- Keep release creation idempotent so reruns can update assets without recreating the release.

## Verification

- Run repository tests and lint locally after the workflow edits.
- Validate shell scripts and inspect the workflow diffs before pushing.
