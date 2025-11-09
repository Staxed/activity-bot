"""Tests for database client."""

from unittest.mock import AsyncMock, MagicMock, patch
from collections.abc import Generator

import asyncpg
import pytest

from app.core.database import DatabaseClient
from app.shared.exceptions import DatabaseError


@pytest.fixture
def mock_settings() -> Generator[MagicMock, None, None]:
    """Mock Settings object for database tests."""
    settings = MagicMock()
    settings.db_host = "localhost"
    settings.db_port = 5432
    settings.db_name = "test_db"
    settings.db_user = "test_user"
    settings.db_password = "test_password"  # noqa: S105
    yield settings


@pytest.mark.asyncio
async def test_database_client_context_manager_lifecycle(mock_settings):
    """Test that DatabaseClient creates and closes pool correctly."""
    with patch("app.core.database.get_settings", return_value=mock_settings):
        with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_pool = AsyncMock()
            mock_create_pool.return_value = mock_pool

            db = DatabaseClient()
            async with db:
                assert db.pool == mock_pool
                mock_create_pool.assert_called_once()

            mock_pool.close.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_all_quotes_success(mock_settings):
    """Test that fetch_all_quotes returns formatted quote tuples."""
    with patch("app.core.database.get_settings", return_value=mock_settings):
        with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_pool = MagicMock()
            mock_conn = AsyncMock()

            # Create async context manager for acquire()
            async_acquire = AsyncMock()
            async_acquire.__aenter__.return_value = mock_conn
            async_acquire.__aexit__.return_value = None
            mock_pool.acquire.return_value = async_acquire

            mock_rows = [
                {"text": "Quote 1", "author": "Author 1"},
                {"text": "Quote 2", "author": "Author 2"},
                {"text": "Quote 3", "author": ""},
            ]
            mock_conn.fetch.return_value = mock_rows
            mock_pool.close = AsyncMock()
            mock_create_pool.return_value = mock_pool

            db = DatabaseClient()
            async with db:
                quotes = await db.fetch_all_quotes()

            assert len(quotes) == 3
            assert quotes[0] == ("Quote 1", "Author 1")
            assert quotes[1] == ("Quote 2", "Author 2")
            assert quotes[2] == ("Quote 3", "")


@pytest.mark.asyncio
async def test_fetch_all_quotes_no_pool_raises():
    """Test that fetch_all_quotes raises DatabaseError when pool is None."""
    db = DatabaseClient()

    with pytest.raises(DatabaseError, match="Connection pool not initialized"):
        await db.fetch_all_quotes()


@pytest.mark.asyncio
async def test_connection_retry_on_failure(mock_settings):
    """Test that connection failures are retried with backoff."""
    with patch("app.core.database.get_settings", return_value=mock_settings):
        with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_create_pool:
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                mock_create_pool.side_effect = [
                    asyncpg.PostgresError("Connection failed"),
                    asyncpg.PostgresError("Connection failed"),
                    AsyncMock(),  # Success on third attempt
                ]

                db = DatabaseClient()
                async with db:
                    assert db.pool is not None

                # Should have retried 2 times
                assert mock_create_pool.call_count == 3
                # Should have slept 2 times (after 1st and 2nd failure)
                assert mock_sleep.call_count == 2
                # Verify backoff delays
                mock_sleep.assert_any_await(2)  # First retry delay
                mock_sleep.assert_any_await(4)  # Second retry delay


@pytest.mark.asyncio
async def test_connection_failure_after_max_retries(mock_settings):
    """Test that DatabaseError is raised after max retries exhausted."""
    with patch("app.core.database.get_settings", return_value=mock_settings):
        with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_create_pool:
            with patch("asyncio.sleep", new_callable=AsyncMock):
                mock_create_pool.side_effect = asyncpg.PostgresError("Connection failed")

                db = DatabaseClient()
                with pytest.raises(DatabaseError, match="Failed to create pool"):
                    async with db:
                        pass

                # Should have attempted 3 times
                assert mock_create_pool.call_count == 3
