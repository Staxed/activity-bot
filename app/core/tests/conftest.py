"""Shared fixtures for core tests."""

from pathlib import Path

import pytest


@pytest.fixture
def temp_state_file(tmp_path: Path) -> Path:
    """Create a temporary state file path for testing.

    Args:
        tmp_path: pytest's temporary directory fixture

    Returns:
        Path to temporary state.json file
    """
    return tmp_path / "state.json"
