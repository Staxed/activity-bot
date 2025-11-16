"""State persistence using JSON file with atomic writes."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Any

from app.core.logging import get_logger
from app.shared.exceptions import StateError

if TYPE_CHECKING:
    from app.core.database import DatabaseClient

logger = get_logger(__name__)


class StateManager:
    """Thread-safe state persistence using JSON file."""

    def __init__(self, file_path: str | Path) -> None:
        """Initialize StateManager with file path.

        Args:
            file_path: Path to JSON state file
        """
        self.file_path = Path(file_path)
        self.lock = Lock()
        self._ensure_file_exists()

    def _ensure_file_exists(self) -> None:
        """Create state file with empty dict if it doesn't exist."""
        if not self.file_path.exists():
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            self.file_path.write_text("{}")
            logger.info("state.file.created", path=str(self.file_path))

    def _read_state(self) -> dict[str, Any]:
        """Read state from JSON file.

        Returns:
            State dictionary, or empty dict if file is corrupted

        Note:
            Returns empty dict instead of raising on JSON decode errors
            to allow graceful recovery from corrupted state files.
        """
        with self.lock:
            try:
                content = self.file_path.read_text()
                result: dict[str, Any] = json.loads(content)
                return result
            except json.JSONDecodeError as e:
                logger.warning(
                    "state.file.corrupted",
                    path=str(self.file_path),
                    error=str(e),
                )
                return {}
            except OSError as e:
                logger.error(
                    "state.file.read_failed",
                    path=str(self.file_path),
                    error=str(e),
                    exc_info=True,
                )
                raise StateError(f"Failed to read state file: {e}") from e

    def _write_state(self, state: dict[str, Any]) -> None:
        """Write state to JSON file atomically.

        Args:
            state: State dictionary to persist

        Note:
            Uses atomic write (temp file + rename) to prevent corruption.
        """
        with self.lock:
            try:
                # Write to temp file first
                temp_path = self.file_path.with_suffix(".tmp")
                temp_path.write_text(json.dumps(state, indent=2))

                # Atomic rename (POSIX-safe)
                temp_path.replace(self.file_path)
            except OSError as e:
                logger.error(
                    "state.file.write_failed",
                    path=str(self.file_path),
                    error=str(e),
                    exc_info=True,
                )
                raise StateError(f"Failed to write state file: {e}") from e

    def get_last_commit_sha(self, owner: str, repo: str) -> str | None:
        """Get the last processed commit SHA for a repository.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            Last processed commit SHA, or None if not tracked
        """
        state = self._read_state()
        repo_key = f"{owner}/{repo}"
        sha: str | None = state.get("last_commit_sha", {}).get(repo_key)
        return sha

    def set_last_commit_sha(self, owner: str, repo: str, sha: str) -> None:
        """Update the last processed commit SHA for a repository.

        Args:
            owner: Repository owner
            repo: Repository name
            sha: Commit SHA to store
        """
        state = self._read_state()

        if "last_commit_sha" not in state:
            state["last_commit_sha"] = {}

        repo_key = f"{owner}/{repo}"
        state["last_commit_sha"][repo_key] = sha

        self._write_state(state)
        logger.info("state.updated", repo=repo_key, sha=sha[:7])

    def get_last_event_id(self) -> str | None:
        """Get the last processed GitHub event ID.

        Returns:
            Last processed event ID, or None if not set
        """
        state = self._read_state()
        event_id: str | None = state.get("last_event_id")
        return event_id

    def set_last_event_id(self, event_id: str) -> None:
        """Update the last processed GitHub event ID.

        Args:
            event_id: Event ID to store
        """
        state = self._read_state()
        state["last_event_id"] = event_id
        self._write_state(state)
        logger.info("state.event_id.updated", event_id=event_id)


async def get_last_event_id_async(db: DatabaseClient) -> str | None:
    """Get last processed event ID from database, fall back to JSON if None.

    Args:
        db: DatabaseClient instance

    Returns:
        Last processed event ID or None
    """
    try:
        event_id = await db.get_last_event_id()
        logger.info("state.async.get_event_id", event_id=event_id, source="database")
        return event_id
    except Exception as e:
        logger.error("state.async.get_failed", error=str(e), exc_info=True)
        return None


async def set_last_event_id_async(db: DatabaseClient, event_id: str) -> None:
    """Set last processed event ID in database.

    Args:
        db: DatabaseClient instance
        event_id: Event ID to store
    """
    try:
        await db.set_last_event_id(event_id)
        logger.info("state.async.set_event_id", event_id=event_id)
    except Exception as e:
        logger.error("state.async.set_failed", error=str(e), exc_info=True)
