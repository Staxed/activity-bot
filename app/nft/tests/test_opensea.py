"""Tests for OpenSea API client."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.nft.marketplaces.opensea import OpenSeaClient


@pytest.fixture
def client() -> OpenSeaClient:
    """Create an OpenSea client."""
    return OpenSeaClient(api_key="test_api_key")


class TestOpenSeaClient:
    """Tests for OpenSeaClient."""

    def test_name_property(self, client: OpenSeaClient) -> None:
        """Test marketplace name."""
        assert client.name == "opensea"

    def test_get_chain_name_base(self, client: OpenSeaClient) -> None:
        """Test chain name mapping for Base."""
        assert client._get_chain_name("base") == "base"

    def test_get_chain_name_ethereum(self, client: OpenSeaClient) -> None:
        """Test chain name mapping for Ethereum."""
        assert client._get_chain_name("ethereum") == "ethereum"

    def test_get_chain_name_polygon(self, client: OpenSeaClient) -> None:
        """Test chain name mapping for Polygon."""
        assert client._get_chain_name("polygon") == "matic"

    def test_get_chain_name_unsupported(self, client: OpenSeaClient) -> None:
        """Test unsupported chain raises error."""
        with pytest.raises(ValueError, match="not supported"):
            client._get_chain_name("solana")

    @pytest.mark.asyncio
    async def test_get_listings_no_collection_id(self, client: OpenSeaClient) -> None:
        """Test that get_listings returns empty when no collection_db_id."""
        result = await client.get_listings(
            contract_address="0x1234",
            chain="base",
            collection_db_id=None,
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_get_sales_no_collection_id(self, client: OpenSeaClient) -> None:
        """Test that get_sales returns empty when no collection_db_id."""
        result = await client.get_sales(
            contract_address="0x1234",
            chain="base",
            collection_db_id=None,
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_close_without_session(self, client: OpenSeaClient) -> None:
        """Test closing client without an active session."""
        await client.close()  # Should not raise


class TestOpenSeaListingParsing:
    """Tests for OpenSea listing response parsing."""

    @pytest.mark.asyncio
    async def test_parse_listing_response(self) -> None:
        """Test parsing a listing from OpenSea API response."""
        client = OpenSeaClient(api_key="test_key")

        # Mock floor price
        client.get_floor_price = AsyncMock(return_value=Decimal("0.1"))

        # Price in wei: 0.5 ETH = 500000000000000000 wei
        mock_listing_data = {
            "orders": [
                {
                    "order_hash": "0xorderhash123",
                    "maker": {"address": "0xseller123"},
                    "listing_time": 1705312200,
                    "cancelled": False,
                    "finalized": False,
                    "protocol_data": {
                        "parameters": {
                            "offer": [{"startAmount": "500000000000000000"}],
                        },
                    },
                    "maker_asset_bundle": {
                        "assets": [
                            {
                                "token_id": "42",
                                "name": "NFT #42",
                                "image_url": "https://example.com/42.png",
                            }
                        ],
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
        assert listing.marketplace == "opensea"
        assert listing.price_native == Decimal("0.5")
        assert listing.listing_id == "0xorderhash123"
        assert listing.is_active is True


class TestOpenSeaSaleParsing:
    """Tests for OpenSea sale response parsing."""

    @pytest.mark.asyncio
    async def test_parse_sale_response(self) -> None:
        """Test parsing a sale from OpenSea API response."""
        client = OpenSeaClient(api_key="test_key")

        # Mock floor price
        client.get_floor_price = AsyncMock(return_value=Decimal("0.1"))

        # Price in wei: 0.75 ETH
        mock_sale_data = {
            "asset_events": [
                {
                    "event_type": "sale",
                    "event_timestamp": "2024-01-15T10:30:00Z",
                    "seller": "0xseller",
                    "buyer": "0xbuyer",
                    "payment": {
                        "quantity": "750000000000000000",
                        "usd_price": "2250.00",
                    },
                    "nft": {
                        "identifier": "99",
                        "name": "NFT #99",
                        "image_url": "https://example.com/99.png",
                    },
                    "transaction": {"hash": "0xtxhash123"},
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
        assert sale.marketplace == "opensea"
        assert sale.price_native == Decimal("0.75")
        assert sale.seller_address == "0xseller"
        assert sale.buyer_address == "0xbuyer"


class TestOpenSeaRateLimiting:
    """Tests for OpenSea rate limit handling."""

    @pytest.mark.asyncio
    async def test_rate_limit_raises_error(self) -> None:
        """Test that 429 response raises RateLimitError."""
        from app.nft.marketplaces.base import RateLimitError

        client = OpenSeaClient(api_key="test_key")

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
    async def test_invalid_api_key_raises_error(self) -> None:
        """Test that 401 response raises APIError."""
        from app.nft.marketplaces.base import APIError

        client = OpenSeaClient(api_key="invalid_key")

        mock_response = MagicMock()
        mock_response.status = 401
        mock_response.text = AsyncMock(return_value="Unauthorized")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.closed = False
        client.session = mock_session

        with pytest.raises(APIError, match="Invalid API key"):
            await client._request("/test")
