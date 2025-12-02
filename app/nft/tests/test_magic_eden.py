"""Tests for Magic Eden API client."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.nft.marketplaces.magic_eden import MagicEdenClient


@pytest.fixture
def client() -> MagicEdenClient:
    """Create a Magic Eden client."""
    return MagicEdenClient()


class TestMagicEdenClient:
    """Tests for MagicEdenClient."""

    def test_name_property(self, client: MagicEdenClient) -> None:
        """Test marketplace name."""
        assert client.name == "magic_eden"

    def test_get_base_url_base_chain(self, client: MagicEdenClient) -> None:
        """Test base URL for Base chain."""
        url = client._get_base_url("base")
        assert "base" in url

    def test_get_base_url_ethereum(self, client: MagicEdenClient) -> None:
        """Test base URL for Ethereum."""
        url = client._get_base_url("ethereum")
        assert "ethereum" in url

    def test_get_base_url_unsupported_chain(self, client: MagicEdenClient) -> None:
        """Test that unsupported chain raises error."""
        with pytest.raises(ValueError, match="not supported"):
            client._get_base_url("solana")

    @pytest.mark.asyncio
    async def test_get_listings_no_collection_id(self, client: MagicEdenClient) -> None:
        """Test that get_listings returns empty when no collection_db_id."""
        result = await client.get_listings(
            contract_address="0x1234",
            chain="base",
            collection_db_id=None,
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_get_sales_no_collection_id(self, client: MagicEdenClient) -> None:
        """Test that get_sales returns empty when no collection_db_id."""
        result = await client.get_sales(
            contract_address="0x1234",
            chain="base",
            collection_db_id=None,
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_close_without_session(self, client: MagicEdenClient) -> None:
        """Test closing client without an active session."""
        await client.close()  # Should not raise

    @pytest.mark.asyncio
    async def test_get_floor_price_returns_decimal(self) -> None:
        """Test floor price parsing returns Decimal."""
        client = MagicEdenClient()

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "collections": [
                    {
                        "floorAsk": {
                            "price": {"amount": {"decimal": "0.25"}},
                        },
                    }
                ]
            }
        )
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.closed = False
        client.session = mock_session

        floor = await client.get_floor_price("0x1234", "base")
        assert floor == Decimal("0.25")

    @pytest.mark.asyncio
    async def test_get_floor_price_returns_none_on_error(self) -> None:
        """Test floor price returns None on API error."""
        client = MagicEdenClient()

        mock_response = MagicMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Server error")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.closed = False
        client.session = mock_session

        floor = await client.get_floor_price("0x1234", "base")
        assert floor is None


class TestMagicEdenListingParsing:
    """Tests for listing response parsing."""

    @pytest.mark.asyncio
    async def test_parse_listing_response(self) -> None:
        """Test parsing a listing from Magic Eden API response."""
        client = MagicEdenClient()

        # Mock floor price
        client.get_floor_price = AsyncMock(return_value=Decimal("0.1"))

        mock_listing_data = {
            "orders": [
                {
                    "id": "order_123",
                    "maker": "0xseller123",
                    "createdAt": "2024-01-15T10:30:00Z",
                    "price": {
                        "amount": {"decimal": "0.5", "usd": "1500"},
                    },
                    "status": "active",
                    "criteria": {
                        "data": {
                            "token": {
                                "tokenId": "42",
                                "name": "NFT #42",
                                "image": "https://example.com/42.png",
                                "rarityRank": 100,
                            },
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
        assert listing.marketplace == "magic_eden"
        assert listing.price_native == Decimal("0.5")
        assert listing.listing_id == "order_123"


class TestMagicEdenSaleParsing:
    """Tests for sale response parsing."""

    @pytest.mark.asyncio
    async def test_parse_sale_response(self) -> None:
        """Test parsing a sale from Magic Eden API response."""
        client = MagicEdenClient()

        # Mock floor price
        client.get_floor_price = AsyncMock(return_value=Decimal("0.1"))

        mock_sale_data = {
            "sales": [
                {
                    "txHash": "0xtx123",
                    "from": "0xseller",
                    "to": "0xbuyer",
                    "timestamp": 1705312200,  # Unix timestamp
                    "price": {
                        "amount": {"decimal": "0.75", "usd": "2250"},
                    },
                    "token": {
                        "tokenId": "99",
                        "name": "NFT #99",
                        "image": "https://example.com/99.png",
                        "rarityRank": 50,
                    },
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
        assert sale.marketplace == "magic_eden"
        assert sale.price_native == Decimal("0.75")
        assert sale.seller_address == "0xseller"
        assert sale.buyer_address == "0xbuyer"
