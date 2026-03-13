"""Tests for python -m traceviz."""

import runpy
from unittest.mock import patch


def test_module_entry_calls_cli_main():
    with patch("traceviz.cli.main") as main:
        runpy.run_module("traceviz", run_name="__main__")

    main.assert_called_once_with()
