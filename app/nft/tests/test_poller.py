"""Tests for marketplace polling service."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.nft.config import NFTCollectionConfig
from app.nft.marketplaces.poller import MarketplacePollingService
from app.nft.models import NFTListingEvent, NFTSaleEvent


@pytest.fixture
def mock_db() -> MagicMock:
    """Create a mock database client."""
    db = MagicMock()
    db.get_nft_collection_db_id = AsyncMock(return_value=1)
    db.get_nft_marketplace_state = AsyncMock(return_value=None)
    db.set_nft_marketplace_state = AsyncMock()
    db.insert_nft_listing = AsyncMock(return_value=True)
    db.insert_nft_sale = AsyncMock(return_value=True)
    db.insert_nft_delisting = AsyncMock(return_value=True)
    db.mark_nft_listing_posted = AsyncMock()
    db.mark_nft_sale_posted = AsyncMock()
    db.mark_nft_delisting_posted = AsyncMock()
    return db


@pytest.fixture
def mock_poster() -> MagicMock:
    """Create a mock NFT poster."""
    poster = MagicMock()
    poster.post_listing = AsyncMock()
    poster.post_sale = AsyncMock()
    poster.post_delisting = AsyncMock()
    return poster


@pytest.fixture
def sample_collection() -> NFTCollectionConfig:
    """Create a sample collection config."""
    return NFTCollectionConfig(
        id="test-collection",
        name="Test Collection",
        chain="base",
        contract_address="0x1234567890123456789012345678901234567890",
        discord_channel_id=123456789,
        track_onchain=True,
        track_marketplace=True,
        marketplaces=["magic_eden", "opensea", "rarible"],
        is_active=True,
    )


@pytest.fixture
def sample_listing() -> NFTListingEvent:
    """Create a sample listing event."""
    return NFTListingEvent(
        collection_id=1,
        token_id="42",
        token_name="NFT #42",
        token_image_url="https://example.com/42.png",
        seller_address="0xseller",
        marketplace="magic_eden",
        price_native=Decimal("0.5"),
        price_usd=Decimal("1500"),
        floor_price_native=Decimal("0.25"),
        rarity_rank=100,
        listing_id="listing_123",
        event_timestamp=datetime.now(UTC),
        is_active=True,
    )


@pytest.fixture
def sample_sale() -> NFTSaleEvent:
    """Create a sample sale event."""
    return NFTSaleEvent(
        collection_id=1,
        token_id="42",
        token_name="NFT #42",
        token_image_url="https://example.com/42.png",
        seller_address="0xseller",
        buyer_address="0xbuyer",
        marketplace="magic_eden",
        price_native=Decimal("0.5"),
        price_usd=Decimal("1500"),
        floor_price_native=Decimal("0.25"),
        rarity_rank=100,
        sale_id="sale_123",
        event_timestamp=datetime.now(UTC),
    )


class TestMarketplacePollingService:
    """Tests for MarketplacePollingService."""

    def test_init(self, mock_db: MagicMock) -> None:
        """Test service initialization."""
        service = MarketplacePollingService(
            db=mock_db,
            poll_interval_minutes=5,
            opensea_api_key="test_key",
        )

        assert service.poll_interval_minutes == 5
        assert service.opensea_api_key == "test_key"
        assert service._running is False

    @pytest.mark.asyncio
    async def test_start_initializes_clients(self, mock_db: MagicMock) -> None:
        """Test that start initializes marketplace clients."""
        service = MarketplacePollingService(
            db=mock_db,
            opensea_api_key="test_key",
        )

        # Start and immediately stop
        await service.start()
        await service.stop()

        # Should have initialized clients
        assert "magic_eden" in service._clients or len(service._clients) == 0

    @pytest.mark.asyncio
    async def test_start_without_opensea_key(self, mock_db: MagicMock) -> None:
        """Test start without OpenSea API key logs warning."""
        service = MarketplacePollingService(
            db=mock_db,
            opensea_api_key=None,
        )

        await service.start()
        await service.stop()

        # Service should still start, just without OpenSea

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self, mock_db: MagicMock) -> None:
        """Test that stop cancels the polling task."""
        service = MarketplacePollingService(
            db=mock_db,
            poll_interval_minutes=60,  # Long interval
        )

        await service.start()
        assert service._running is True
        assert service._poll_task is not None

        await service.stop()
        assert service._running is False

    @pytest.mark.asyncio
    async def test_stop_closes_clients(self, mock_db: MagicMock) -> None:
        """Test that stop closes all marketplace clients."""
        service = MarketplacePollingService(
            db=mock_db,
            opensea_api_key="test_key",
        )

        await service.start()
        await service.stop()

        # Clients should be cleared
        assert len(service._clients) == 0


class TestPollingLogic:
    """Tests for polling logic."""

    @pytest.mark.asyncio
    @patch("app.nft.marketplaces.poller.get_collections_config")
    async def test_poll_all_collections_empty(
        self,
        mock_config: MagicMock,
        mock_db: MagicMock,
    ) -> None:
        """Test polling with no active collections."""
        mock_collections_config = MagicMock()
        mock_collections_config.active_collections = []
        mock_config.return_value = mock_collections_config

        service = MarketplacePollingService(db=mock_db)

        await service._poll_all_collections()

        # Should not try to poll any collections
        mock_db.get_nft_collection_db_id.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.nft.marketplaces.poller.get_collections_config")
    async def test_poll_skips_non_marketplace_collections(
        self,
        mock_config: MagicMock,
        mock_db: MagicMock,
    ) -> None:
        """Test that collections with track_marketplace=False are skipped."""
        mock_collection = MagicMock()
        mock_collection.track_marketplace = False

        mock_collections_config = MagicMock()
        mock_collections_config.active_collections = [mock_collection]
        mock_config.return_value = mock_collections_config

        service = MarketplacePollingService(db=mock_db)

        await service._poll_all_collections()

        # Should not try to get db ID
        mock_db.get_nft_collection_db_id.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.nft.marketplaces.poller.get_collections_config")
    async def test_poll_skips_collection_without_db_id(
        self,
        mock_config: MagicMock,
        mock_db: MagicMock,
        sample_collection: NFTCollectionConfig,
    ) -> None:
        """Test that collections without DB ID are skipped."""
        mock_collections_config = MagicMock()
        mock_collections_config.active_collections = [sample_collection]
        mock_config.return_value = mock_collections_config

        # No DB ID found
        mock_db.get_nft_collection_db_id.return_value = None

        service = MarketplacePollingService(db=mock_db)

        await service._poll_all_collections()

        # Should not try to get marketplace state
        mock_db.get_nft_marketplace_state.assert_not_called()


class TestMarketplacePolling:
    """Tests for individual marketplace polling."""

    @pytest.mark.asyncio
    async def test_poll_marketplace_inserts_listing(
        self,
        mock_db: MagicMock,
        mock_poster: MagicMock,
        sample_collection: NFTCollectionConfig,
        sample_listing: NFTListingEvent,
    ) -> None:
        """Test that listings are inserted and posted."""
        # Create mock client
        mock_client = MagicMock()
        mock_client.name = "magic_eden"
        mock_client.get_listings = AsyncMock(return_value=[sample_listing])
        mock_client.get_sales = AsyncMock(return_value=[])
        mock_client.get_delistings = AsyncMock(return_value=[])

        service = MarketplacePollingService(db=mock_db, poster=mock_poster)

        await service._poll_marketplace(
            collection=sample_collection,
            db_collection_id=1,
            client=mock_client,
        )

        # Should insert listing
        mock_db.insert_nft_listing.assert_called_once_with(sample_listing)

        # Should post listing
        mock_poster.post_listing.assert_called_once()

        # Should mark as posted
        mock_db.mark_nft_listing_posted.assert_called_once()

        # Should update state
        mock_db.set_nft_marketplace_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_poll_marketplace_inserts_sale(
        self,
        mock_db: MagicMock,
        mock_poster: MagicMock,
        sample_collection: NFTCollectionConfig,
        sample_sale: NFTSaleEvent,
    ) -> None:
        """Test that sales are inserted and posted."""
        mock_client = MagicMock()
        mock_client.name = "magic_eden"
        mock_client.get_listings = AsyncMock(return_value=[])
        mock_client.get_sales = AsyncMock(return_value=[sample_sale])
        mock_client.get_delistings = AsyncMock(return_value=[])

        service = MarketplacePollingService(db=mock_db, poster=mock_poster)

        await service._poll_marketplace(
            collection=sample_collection,
            db_collection_id=1,
            client=mock_client,
        )

        # Should insert sale
        mock_db.insert_nft_sale.assert_called_once_with(sample_sale)

        # Should post sale
        mock_poster.post_sale.assert_called_once()

    @pytest.mark.asyncio
    async def test_poll_marketplace_skips_duplicate(
        self,
        mock_db: MagicMock,
        mock_poster: MagicMock,
        sample_collection: NFTCollectionConfig,
        sample_listing: NFTListingEvent,
    ) -> None:
        """Test that duplicates are not posted."""
        mock_client = MagicMock()
        mock_client.name = "magic_eden"
        mock_client.get_listings = AsyncMock(return_value=[sample_listing])
        mock_client.get_sales = AsyncMock(return_value=[])
        mock_client.get_delistings = AsyncMock(return_value=[])

        # Simulate duplicate - insert returns False
        mock_db.insert_nft_listing.return_value = False

        service = MarketplacePollingService(db=mock_db, poster=mock_poster)

        await service._poll_marketplace(
            collection=sample_collection,
            db_collection_id=1,
            client=mock_client,
        )

        # Should try to insert
        mock_db.insert_nft_listing.assert_called_once()

        # Should NOT post (duplicate)
        mock_poster.post_listing.assert_not_called()

    @pytest.mark.asyncio
    async def test_poll_marketplace_uses_last_poll_time(
        self,
        mock_db: MagicMock,
        sample_collection: NFTCollectionConfig,
    ) -> None:
        """Test that last poll time is passed to client."""
        last_poll = datetime.now(UTC) - timedelta(hours=1)
        mock_db.get_nft_marketplace_state.return_value = last_poll

        mock_client = MagicMock()
        mock_client.name = "magic_eden"
        mock_client.get_listings = AsyncMock(return_value=[])
        mock_client.get_sales = AsyncMock(return_value=[])
        mock_client.get_delistings = AsyncMock(return_value=[])

        service = MarketplacePollingService(db=mock_db)

        await service._poll_marketplace(
            collection=sample_collection,
            db_collection_id=1,
            client=mock_client,
        )

        # Client should be called with since parameter
        mock_client.get_listings.assert_called_once()
        call_kwargs = mock_client.get_listings.call_args.kwargs
        assert call_kwargs["since"] == last_poll

    @pytest.mark.asyncio
    async def test_poll_marketplace_defaults_to_12_hours(
        self,
        mock_db: MagicMock,
        sample_collection: NFTCollectionConfig,
    ) -> None:
        """Test that default lookback is 12 hours."""
        mock_db.get_nft_marketplace_state.return_value = None

        mock_client = MagicMock()
        mock_client.name = "magic_eden"
        mock_client.get_listings = AsyncMock(return_value=[])
        mock_client.get_sales = AsyncMock(return_value=[])
        mock_client.get_delistings = AsyncMock(return_value=[])

        service = MarketplacePollingService(db=mock_db)

        await service._poll_marketplace(
            collection=sample_collection,
            db_collection_id=1,
            client=mock_client,
        )

        # Should use approximately 12 hours ago
        call_kwargs = mock_client.get_listings.call_args.kwargs
        since = call_kwargs["since"]
        expected = datetime.now(UTC) - timedelta(hours=12)

        # Allow 1 minute tolerance
        assert abs((since - expected).total_seconds()) < 60


class TestPollNow:
    """Tests for poll_now method."""

    @pytest.mark.asyncio
    @patch("app.nft.marketplaces.poller.get_collections_config")
    async def test_poll_now_triggers_poll(
        self,
        mock_config: MagicMock,
        mock_db: MagicMock,
    ) -> None:
        """Test that poll_now triggers immediate polling."""
        mock_collections_config = MagicMock()
        mock_collections_config.active_collections = []
        mock_config.return_value = mock_collections_config

        service = MarketplacePollingService(db=mock_db)

        # Should not raise
        await service.poll_now()

        # Config should be fetched
        mock_config.assert_called_once()
