"""Tests for Rarible API client."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.nft.marketplaces.rarible import RaribleClient


@pytest.fixture
def client() -> RaribleClient:
    """Create a Rarible client."""
    return RaribleClient()


class TestRaribleClient:
    """Tests for RaribleClient."""

    def test_name_property(self, client: RaribleClient) -> None:
        """Test marketplace name."""
        assert client.name == "rarible"

    def test_get_blockchain_base(self, client: RaribleClient) -> None:
        """Test blockchain mapping for Base."""
        assert client._get_blockchain("base") == "BASE"

    def test_get_blockchain_ethereum(self, client: RaribleClient) -> None:
        """Test blockchain mapping for Ethereum."""
        assert client._get_blockchain("ethereum") == "ETHEREUM"

    def test_get_blockchain_polygon(self, client: RaribleClient) -> None:
        """Test blockchain mapping for Polygon."""
        assert client._get_blockchain("polygon") == "POLYGON"

    def test_get_blockchain_unsupported(self, client: RaribleClient) -> None:
        """Test unsupported chain raises error."""
        with pytest.raises(ValueError, match="not supported"):
            client._get_blockchain("solana")

    def test_format_item_id_with_token(self, client: RaribleClient) -> None:
        """Test item ID formatting with token ID."""
        item_id = client._format_item_id("base", "0xABC123", "42")
        assert item_id == "BASE:0xabc123:42"

    def test_format_item_id_without_token(self, client: RaribleClient) -> None:
        """Test item ID formatting without token ID."""
        item_id = client._format_item_id("ethereum", "0xABC123")
        assert item_id == "ETHEREUM:0xabc123"

    @pytest.mark.asyncio
    async def test_get_listings_no_collection_id(self, client: RaribleClient) -> None:
        """Test that get_listings returns empty when no collection_db_id."""
        result = await client.get_listings(
            contract_address="0x1234",
            chain="base",
            collection_db_id=None,
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_get_sales_no_collection_id(self, client: RaribleClient) -> None:
        """Test that get_sales returns empty when no collection_db_id."""
        result = await client.get_sales(
            contract_address="0x1234",
            chain="base",
            collection_db_id=None,
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_close_without_session(self, client: RaribleClient) -> None:
        """Test closing client without an active session."""
        await client.close()  # Should not raise


class TestRaribleListingParsing:
    """Tests for Rarible listing response parsing."""

    @pytest.mark.asyncio
    async def test_parse_listing_response(self) -> None:
        """Test parsing a listing from Rarible API response."""
        client = RaribleClient()

        # Mock floor price
        client.get_floor_price = AsyncMock(return_value=Decimal("0.1"))

        mock_listing_data = {
            "orders": [
                {
                    "id": "order_123",
                    "maker": "BASE:0xseller123",
                    "createdAt": "2024-01-15T10:30:00Z",
                    "makePrice": "0.5",
                    "makePriceUsd": "1500",
                    "status": "ACTIVE",
                    "make": {
                        "type": {
                            "itemId": "BASE:0x1234:42",
                        },
                        "value": "1",
                    },
                    "nft": {
                        "meta": {
                            "name": "NFT #42",
                            "content": [{"url": "https://example.com/42.png"}],
                        },
                    },
                }
            ]
        }

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_listing_data)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.closed = False
        client.session = mock_session

        listings = await client.get_listings(
            contract_address="0x1234",
            chain="base",
            collection_db_id=1,
        )

        assert len(listings) == 1
        listing = listings[0]
        assert listing.token_id == "42"
        assert listing.marketplace == "rarible"
        assert listing.price_native == Decimal("0.5")
        assert listing.listing_id == "order_123"
        assert listing.is_active is True
        assert listing.seller_address == "0xseller123"


class TestRaribleSaleParsing:
    """Tests for Rarible sale response parsing."""

    @pytest.mark.asyncio
    async def test_parse_sale_response(self) -> None:
        """Test parsing a sale from Rarible API response."""
        client = RaribleClient()

        # Mock floor price
        client.get_floor_price = AsyncMock(return_value=Decimal("0.1"))

        mock_sale_data = {
            "activities": [
                {
                    "@type": "SELL",
                    "id": "sale_123",
                    "date": "2024-01-15T10:30:00Z",
                    "seller": "BASE:0xseller",
                    "buyer": "BASE:0xbuyer",
                    "price": "0.75",
                    "priceUsd": "2250",
                    "nft": {
                        "id": "BASE:0x1234:99",
                        "meta": {
                            "name": "NFT #99",
                            "content": [{"url": "https://example.com/99.png"}],
                        },
                    },
                    "transactionHash": "0xtxhash123",
                }
            ]
        }

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_sale_data)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.closed = False
        client.session = mock_session

        sales = await client.get_sales(
            contract_address="0x1234",
            chain="base",
            collection_db_id=1,
        )

        assert len(sales) == 1
        sale = sales[0]
        assert sale.token_id == "99"
        assert sale.marketplace == "rarible"
        assert sale.price_native == Decimal("0.75")
        assert sale.seller_address == "0xseller"
        assert sale.buyer_address == "0xbuyer"


class TestRaribleFloorPrice:
    """Tests for Rarible floor price fetching."""

    @pytest.mark.asyncio
    async def test_get_floor_price_returns_decimal(self) -> None:
        """Test floor price returns Decimal."""
        client = RaribleClient()

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"floorPrice": "0.25"})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.closed = False
        client.session = mock_session

        floor = await client.get_floor_price("0x1234", "base")
        assert floor == Decimal("0.25")

    @pytest.mark.asyncio
    async def test_get_floor_price_returns_none_when_missing(self) -> None:
        """Test floor price returns None when not in response."""
        client = RaribleClient()

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.closed = False
        client.session = mock_session

        floor = await client.get_floor_price("0x1234", "base")
        assert floor is None


class TestRaribleRateLimiting:
    """Tests for Rarible rate limit handling."""

    @pytest.mark.asyncio
    async def test_rate_limit_raises_error(self) -> None:
        """Test that 429 response raises RateLimitError."""
        from app.nft.marketplaces.base import RateLimitError

        client = RaribleClient()

        mock_response = MagicMock()
        mock_response.status = 429
        mock_response.headers = {"Retry-After": "60"}
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.closed = False
        client.session = mock_session

        with pytest.raises(RateLimitError):
            await client._request("/test")

    @pytest.mark.asyncio
    async def test_api_error_raises_exception(self) -> None:
        """Test that non-200 response raises APIError."""
        from app.nft.marketplaces.base import APIError

        client = RaribleClient()

        mock_response = MagicMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Server error")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.closed = False
        client.session = mock_session

        with pytest.raises(APIError):
            await client._request("/test")
