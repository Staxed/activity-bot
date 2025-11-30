"""Tests for Thirdweb webhook event handler."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.nft.models import ZERO_ADDRESS
from app.nft.thirdweb.handler import ThirdwebEventHandler


@pytest.fixture
def mock_db() -> MagicMock:
    """Create a mock database client."""
    db = MagicMock()
    db.get_nft_collection_db_id = AsyncMock(return_value=1)
    db.insert_nft_mint = AsyncMock(return_value=True)
    db.insert_nft_transfer = AsyncMock(return_value=True)
    db.insert_nft_burn = AsyncMock(return_value=True)
    db.mark_nft_mint_posted = AsyncMock()
    db.mark_nft_transfer_posted = AsyncMock()
    db.mark_nft_burn_posted = AsyncMock()
    return db


@pytest.fixture
def mock_poster() -> MagicMock:
    """Create a mock NFT poster."""
    poster = MagicMock()
    poster.post_mint = AsyncMock()
    poster.post_transfer = AsyncMock()
    poster.post_burn = AsyncMock()
    return poster


@pytest.fixture
def handler(mock_db: MagicMock, mock_poster: MagicMock) -> ThirdwebEventHandler:
    """Create handler with mocked dependencies."""
    return ThirdwebEventHandler(db=mock_db, poster=mock_poster)


class TestThirdwebEventHandler:
    """Tests for ThirdwebEventHandler."""

    @pytest.mark.asyncio
    async def test_handle_event_skips_non_transfer(self, handler: ThirdwebEventHandler) -> None:
        """Test that non-transfer events are skipped."""
        payload = {"type": "approval", "data": {}}

        await handler.handle_event(payload)

        # Should not try to look up collection
        handler.db.get_nft_collection_db_id.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.nft.thirdweb.handler.get_collections_config")
    async def test_handle_mint_event(
        self,
        mock_config: MagicMock,
        handler: ThirdwebEventHandler,
    ) -> None:
        """Test handling a mint event (from zero address)."""
        # Setup mock config
        mock_collection = MagicMock()
        mock_collection.id = "test-collection"
        mock_collection.name = "Test Collection"
        mock_collection.track_onchain = True
        mock_collection.discord_channel_id = 123456789

        mock_collections_config = MagicMock()
        mock_collections_config.get_collection_by_contract.return_value = mock_collection
        mock_config.return_value = mock_collections_config

        payload = {
            "type": "transfer",
            "data": {
                "contractAddress": "0x1234567890123456789012345678901234567890",
                "chain": "base",
                "from": ZERO_ADDRESS,  # Mint: from zero address
                "to": "0xabcdef1234567890abcdef1234567890abcdef12",
                "tokenId": "42",
                "transactionHash": "0xtxhash123",
                "blockNumber": 12345,
                "timestamp": int(datetime.now(UTC).timestamp()),
            },
        }

        await handler.handle_event(payload)

        # Should insert mint event
        handler.db.insert_nft_mint.assert_called_once()
        handler.poster.post_mint.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.nft.thirdweb.handler.get_collections_config")
    async def test_handle_burn_event(
        self,
        mock_config: MagicMock,
        handler: ThirdwebEventHandler,
    ) -> None:
        """Test handling a burn event (to zero address)."""
        # Setup mock config
        mock_collection = MagicMock()
        mock_collection.id = "test-collection"
        mock_collection.name = "Test Collection"
        mock_collection.track_onchain = True
        mock_collection.discord_channel_id = 123456789

        mock_collections_config = MagicMock()
        mock_collections_config.get_collection_by_contract.return_value = mock_collection
        mock_config.return_value = mock_collections_config

        payload = {
            "type": "transfer",
            "data": {
                "contractAddress": "0x1234567890123456789012345678901234567890",
                "chain": "base",
                "from": "0xabcdef1234567890abcdef1234567890abcdef12",
                "to": ZERO_ADDRESS,  # Burn: to zero address
                "tokenId": "42",
                "transactionHash": "0xtxhash123",
                "blockNumber": 12345,
                "timestamp": int(datetime.now(UTC).timestamp()),
            },
        }

        await handler.handle_event(payload)

        # Should insert burn event
        handler.db.insert_nft_burn.assert_called_once()
        handler.poster.post_burn.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.nft.thirdweb.handler.get_collections_config")
    async def test_handle_transfer_event(
        self,
        mock_config: MagicMock,
        handler: ThirdwebEventHandler,
    ) -> None:
        """Test handling a regular transfer event."""
        # Setup mock config
        mock_collection = MagicMock()
        mock_collection.id = "test-collection"
        mock_collection.name = "Test Collection"
        mock_collection.track_onchain = True
        mock_collection.discord_channel_id = 123456789

        mock_collections_config = MagicMock()
        mock_collections_config.get_collection_by_contract.return_value = mock_collection
        mock_config.return_value = mock_collections_config

        payload = {
            "type": "transfer",
            "data": {
                "contractAddress": "0x1234567890123456789012345678901234567890",
                "chain": "base",
                "from": "0xabcdef1234567890abcdef1234567890abcdef12",
                "to": "0x1111111111111111111111111111111111111111",  # Regular transfer
                "tokenId": "42",
                "transactionHash": "0xtxhash123",
                "blockNumber": 12345,
                "timestamp": int(datetime.now(UTC).timestamp()),
            },
        }

        await handler.handle_event(payload)

        # Should insert transfer event
        handler.db.insert_nft_transfer.assert_called_once()
        handler.poster.post_transfer.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.nft.thirdweb.handler.get_collections_config")
    async def test_handle_event_unknown_collection(
        self,
        mock_config: MagicMock,
        handler: ThirdwebEventHandler,
    ) -> None:
        """Test that unknown collections are skipped."""
        mock_collections_config = MagicMock()
        mock_collections_config.get_collection_by_contract.return_value = None
        mock_config.return_value = mock_collections_config

        payload = {
            "type": "transfer",
            "data": {
                "contractAddress": "0xunknown",
                "chain": "base",
                "from": ZERO_ADDRESS,
                "to": "0xabcdef",
                "tokenId": "1",
                "transactionHash": "0x123",
                "blockNumber": 1,
                "timestamp": int(datetime.now(UTC).timestamp()),
            },
        }

        await handler.handle_event(payload)

        # Should not try to insert any events
        handler.db.insert_nft_mint.assert_not_called()
        handler.db.insert_nft_transfer.assert_not_called()
        handler.db.insert_nft_burn.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.nft.thirdweb.handler.get_collections_config")
    async def test_handle_event_tracking_disabled(
        self,
        mock_config: MagicMock,
        handler: ThirdwebEventHandler,
    ) -> None:
        """Test that events are skipped when on-chain tracking is disabled."""
        mock_collection = MagicMock()
        mock_collection.id = "test-collection"
        mock_collection.track_onchain = False  # Tracking disabled

        mock_collections_config = MagicMock()
        mock_collections_config.get_collection_by_contract.return_value = mock_collection
        mock_config.return_value = mock_collections_config

        payload = {
            "type": "transfer",
            "data": {
                "contractAddress": "0x1234567890123456789012345678901234567890",
                "chain": "base",
                "from": ZERO_ADDRESS,
                "to": "0xabcdef",
                "tokenId": "1",
                "transactionHash": "0x123",
                "blockNumber": 1,
                "timestamp": int(datetime.now(UTC).timestamp()),
            },
        }

        await handler.handle_event(payload)

        # Should not insert any events
        handler.db.insert_nft_mint.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.nft.thirdweb.handler.get_collections_config")
    async def test_handle_duplicate_event(
        self,
        mock_config: MagicMock,
        handler: ThirdwebEventHandler,
    ) -> None:
        """Test that duplicate events are not posted to Discord."""
        mock_collection = MagicMock()
        mock_collection.id = "test-collection"
        mock_collection.name = "Test Collection"
        mock_collection.track_onchain = True
        mock_collection.discord_channel_id = 123456789

        mock_collections_config = MagicMock()
        mock_collections_config.get_collection_by_contract.return_value = mock_collection
        mock_config.return_value = mock_collections_config

        # Simulate duplicate - insert returns False
        handler.db.insert_nft_mint.return_value = False

        payload = {
            "type": "transfer",
            "data": {
                "contractAddress": "0x1234567890123456789012345678901234567890",
                "chain": "base",
                "from": ZERO_ADDRESS,
                "to": "0xabcdef",
                "tokenId": "42",
                "transactionHash": "0xduplicate",
                "blockNumber": 12345,
                "timestamp": int(datetime.now(UTC).timestamp()),
            },
        }

        await handler.handle_event(payload)

        # Should try to insert but not post to Discord
        handler.db.insert_nft_mint.assert_called_once()
        handler.poster.post_mint.assert_not_called()


class TestChainMapping:
    """Tests for chain name mapping."""

    @pytest.mark.asyncio
    @patch("app.nft.thirdweb.handler.get_collections_config")
    async def test_chain_mapping_base_mainnet(
        self,
        mock_config: MagicMock,
        handler: ThirdwebEventHandler,
    ) -> None:
        """Test that 'base-mainnet' is mapped to 'base'."""
        mock_collections_config = MagicMock()
        mock_collections_config.get_collection_by_contract.return_value = None
        mock_config.return_value = mock_collections_config

        payload = {
            "type": "transfer",
            "data": {
                "contractAddress": "0x1234",
                "chain": "base-mainnet",  # Should be mapped to "base"
                "from": ZERO_ADDRESS,
                "to": "0xabcdef",
                "tokenId": "1",
                "transactionHash": "0x123",
                "blockNumber": 1,
                "timestamp": int(datetime.now(UTC).timestamp()),
            },
        }

        await handler.handle_event(payload)

        # Should look up with mapped chain name
        mock_collections_config.get_collection_by_contract.assert_called_with("base", "0x1234")

    @pytest.mark.asyncio
    @patch("app.nft.thirdweb.handler.get_collections_config")
    async def test_chain_mapping_eth_mainnet(
        self,
        mock_config: MagicMock,
        handler: ThirdwebEventHandler,
    ) -> None:
        """Test that 'eth-mainnet' is mapped to 'ethereum'."""
        mock_collections_config = MagicMock()
        mock_collections_config.get_collection_by_contract.return_value = None
        mock_config.return_value = mock_collections_config

        payload = {
            "type": "transfer",
            "data": {
                "contractAddress": "0x1234",
                "chain": "eth-mainnet",  # Should be mapped to "ethereum"
                "from": ZERO_ADDRESS,
                "to": "0xabcdef",
                "tokenId": "1",
                "transactionHash": "0x123",
                "blockNumber": 1,
                "timestamp": int(datetime.now(UTC).timestamp()),
            },
        }

        await handler.handle_event(payload)

        # Should look up with mapped chain name
        mock_collections_config.get_collection_by_contract.assert_called_with("ethereum", "0x1234")
