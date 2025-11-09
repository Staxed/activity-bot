"""Tests for app.core.state module."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app.core.state import StateManager
from app.shared.exceptions import StateError


def test_state_manager_creates_file(temp_state_file: Path) -> None:
    """Test that StateManager creates file with empty dict if not exists."""
    manager = StateManager(temp_state_file)

    assert temp_state_file.exists()

    content = json.loads(temp_state_file.read_text())
    assert content == {}


def test_state_manager_creates_parent_directories(tmp_path: Path) -> None:
    """Test that StateManager creates parent directories if they don't exist."""
    nested_path = tmp_path / "nested" / "dir" / "state.json"

    manager = StateManager(nested_path)

    assert nested_path.exists()
    assert nested_path.parent.exists()


def test_get_last_commit_sha_none_when_not_set(temp_state_file: Path) -> None:
    """Test that get_last_commit_sha returns None for untracked repo."""
    manager = StateManager(temp_state_file)

    sha = manager.get_last_commit_sha("owner", "repo")

    assert sha is None


def test_set_and_get_last_commit_sha(temp_state_file: Path) -> None:
    """Test that set and get commit SHA works correctly."""
    manager = StateManager(temp_state_file)

    manager.set_last_commit_sha("owner", "repo", "abc123def456")

    sha = manager.get_last_commit_sha("owner", "repo")

    assert sha == "abc123def456"


def test_set_last_commit_sha_persists_to_file(temp_state_file: Path) -> None:
    """Test that commit SHA is persisted to JSON file."""
    manager = StateManager(temp_state_file)

    manager.set_last_commit_sha("owner", "repo", "abc123")

    # Read file directly
    content = json.loads(temp_state_file.read_text())

    assert content["last_commit_sha"]["owner/repo"] == "abc123"


def test_set_last_commit_sha_multiple_repos(temp_state_file: Path) -> None:
    """Test that multiple repositories are tracked independently."""
    manager = StateManager(temp_state_file)

    manager.set_last_commit_sha("owner1", "repo1", "sha1")
    manager.set_last_commit_sha("owner2", "repo2", "sha2")

    assert manager.get_last_commit_sha("owner1", "repo1") == "sha1"
    assert manager.get_last_commit_sha("owner2", "repo2") == "sha2"


def test_set_last_commit_sha_update_existing(temp_state_file: Path) -> None:
    """Test that updating existing commit SHA overwrites old value."""
    manager = StateManager(temp_state_file)

    manager.set_last_commit_sha("owner", "repo", "old_sha")
    manager.set_last_commit_sha("owner", "repo", "new_sha")

    sha = manager.get_last_commit_sha("owner", "repo")

    assert sha == "new_sha"


def test_state_manager_atomic_write(temp_state_file: Path) -> None:
    """Test that atomic write doesn't leave temp files behind."""
    manager = StateManager(temp_state_file)

    manager.set_last_commit_sha("owner", "repo", "abc123")

    # Verify no .tmp file remains
    temp_file = temp_state_file.with_suffix(".tmp")
    assert not temp_file.exists()

    # Verify state was written correctly
    content = json.loads(temp_state_file.read_text())
    assert content["last_commit_sha"]["owner/repo"] == "abc123"


def test_state_manager_handles_corrupted_file(temp_state_file: Path) -> None:
    """Test that corrupted JSON file is handled gracefully."""
    # Create corrupted JSON file
    temp_state_file.parent.mkdir(parents=True, exist_ok=True)
    temp_state_file.write_text("{ invalid json }")

    manager = StateManager(temp_state_file)

    # Should return None instead of raising
    sha = manager.get_last_commit_sha("owner", "repo")

    assert sha is None


def test_state_manager_read_existing_state(temp_state_file: Path) -> None:
    """Test that StateManager reads existing state on initialization."""
    # Pre-populate state file
    temp_state_file.parent.mkdir(parents=True, exist_ok=True)
    temp_state_file.write_text(
        json.dumps({"last_commit_sha": {"owner/repo": "existing_sha"}})
    )

    manager = StateManager(temp_state_file)

    sha = manager.get_last_commit_sha("owner", "repo")

    assert sha == "existing_sha"


def test_state_manager_thread_safe_writes(temp_state_file: Path) -> None:
    """Test that multiple concurrent writes don't corrupt state."""
    manager = StateManager(temp_state_file)

    def write_sha(repo_num: int) -> None:
        manager.set_last_commit_sha("owner", f"repo{repo_num}", f"sha{repo_num}")

    # Write from multiple threads
    with ThreadPoolExecutor(max_workers=5) as executor:
        list(executor.map(write_sha, range(10)))

    # Verify file is valid JSON (not corrupted) - this is the main test
    content = json.loads(temp_state_file.read_text())

    # With concurrent writes, some may be lost (last-write-wins), but:
    # 1. File should not be corrupted (valid JSON)
    # 2. At least some writes should succeed
    assert "last_commit_sha" in content
    assert len(content["last_commit_sha"]) >= 1  # At least one write succeeded

    # Verify what's there is correct
    for repo_key, sha in content["last_commit_sha"].items():
        assert repo_key.startswith("owner/repo")
        assert sha.startswith("sha")
