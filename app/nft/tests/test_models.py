"""Tests for NFT Pydantic models."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.nft.models import (
    ZERO_ADDRESS,
    NFTBurnEvent,
    NFTDelistingEvent,
    NFTListingEvent,
    NFTMintEvent,
    NFTSaleEvent,
    NFTTransferEvent,
)


class TestNFTMintEvent:
    """Tests for NFTMintEvent model."""

    def test_create_mint_event(self, sample_mint_event: NFTMintEvent) -> None:
        """Test creating a mint event."""
        assert sample_mint_event.token_id == "123"
        assert sample_mint_event.collection_id == 1
        assert sample_mint_event.price_native == Decimal("0.05")

    def test_address_normalized_to_lowercase(self) -> None:
        """Test that addresses are normalized to lowercase."""
        event = NFTMintEvent(
            collection_id=1,
            token_id="1",
            to_address="0xABCDEF1234567890ABCDEF1234567890ABCDEF12",
            event_timestamp=datetime.now(UTC),
        )
        assert event.to_address == "0xabcdef1234567890abcdef1234567890abcdef12"

    def test_short_address(self, sample_mint_event: NFTMintEvent) -> None:
        """Test shortened address formatting."""
        assert sample_mint_event.short_to_address == "0xabcd...ef12"

    def test_from_thirdweb_webhook(self) -> None:
        """Test creating from Thirdweb webhook data."""
        timestamp = datetime.now(UTC)
        event = NFTMintEvent.from_thirdweb_webhook(
            collection_id=1,
            token_id="123",
            to_address="0xabcdef1234567890abcdef1234567890abcdef12",
            transaction_hash="0x1234",
            block_number=12345,
            timestamp=timestamp,
            price_native=Decimal("0.1"),
        )

        assert event.token_id == "123"
        assert event.to_address == "0xabcdef1234567890abcdef1234567890abcdef12"
        assert event.block_number == 12345
        assert event.price_native == Decimal("0.1")


class TestNFTTransferEvent:
    """Tests for NFTTransferEvent model."""

    def test_create_transfer_event(self, sample_transfer_event: NFTTransferEvent) -> None:
        """Test creating a transfer event."""
        assert sample_transfer_event.token_id == "123"
        assert "abcd" in sample_transfer_event.short_from_address
        assert "5678" in sample_transfer_event.short_to_address

    def test_from_thirdweb_webhook(self) -> None:
        """Test creating from Thirdweb webhook data."""
        timestamp = datetime.now(UTC)
        event = NFTTransferEvent.from_thirdweb_webhook(
            collection_id=1,
            token_id="123",
            from_address="0xabcd",
            to_address="0x1234",
            transaction_hash="0x5678",
            block_number=100,
            timestamp=timestamp,
        )

        assert event.token_id == "123"
        assert event.from_address == "0xabcd"
        assert event.to_address == "0x1234"


class TestNFTBurnEvent:
    """Tests for NFTBurnEvent model."""

    def test_create_burn_event(self, sample_burn_event: NFTBurnEvent) -> None:
        """Test creating a burn event."""
        assert sample_burn_event.token_id == "123"
        assert sample_burn_event.from_address.startswith("0x")

    def test_from_thirdweb_webhook(self) -> None:
        """Test creating from Thirdweb webhook data."""
        timestamp = datetime.now(UTC)
        event = NFTBurnEvent.from_thirdweb_webhook(
            collection_id=1,
            token_id="456",
            from_address="0xburner",
            transaction_hash="0xburn",
            block_number=999,
            timestamp=timestamp,
        )

        assert event.token_id == "456"
        assert event.from_address == "0xburner"


class TestNFTListingEvent:
    """Tests for NFTListingEvent model."""

    def test_create_listing_event(self, sample_listing_event: NFTListingEvent) -> None:
        """Test creating a listing event."""
        assert sample_listing_event.token_id == "123"
        assert sample_listing_event.marketplace == "magic_eden"
        assert sample_listing_event.price_native == Decimal("0.5")
        assert sample_listing_event.floor_price_native == Decimal("0.25")

    def test_floor_multiple(self, sample_listing_event: NFTListingEvent) -> None:
        """Test floor multiple calculation."""
        # Price is 0.5, floor is 0.25, so 2x floor
        assert sample_listing_event.floor_multiple == pytest.approx(2.0)

    def test_floor_multiple_no_floor(self) -> None:
        """Test floor multiple returns None when no floor."""
        event = NFTListingEvent(
            collection_id=1,
            token_id="1",
            seller_address="0x1234",
            marketplace="opensea",
            price_native=Decimal("1.0"),
            floor_price_native=None,
            listing_id="list_1",
            event_timestamp=datetime.now(UTC),
        )
        assert event.floor_multiple is None

    def test_marketplace_normalized(self) -> None:
        """Test marketplace name is normalized to lowercase."""
        event = NFTListingEvent(
            collection_id=1,
            token_id="1",
            seller_address="0x1234",
            marketplace="MAGIC_EDEN",
            price_native=Decimal("1.0"),
            listing_id="list_1",
            event_timestamp=datetime.now(UTC),
        )
        assert event.marketplace == "magic_eden"


class TestNFTSaleEvent:
    """Tests for NFTSaleEvent model."""

    def test_create_sale_event(self, sample_sale_event: NFTSaleEvent) -> None:
        """Test creating a sale event."""
        assert sample_sale_event.token_id == "123"
        assert sample_sale_event.marketplace == "magic_eden"
        assert sample_sale_event.seller_address.startswith("0x")
        assert sample_sale_event.buyer_address.startswith("0x")

    def test_short_addresses(self, sample_sale_event: NFTSaleEvent) -> None:
        """Test shortened address formatting for both parties."""
        assert "..." in sample_sale_event.short_seller_address
        assert "..." in sample_sale_event.short_buyer_address

    def test_floor_multiple(self, sample_sale_event: NFTSaleEvent) -> None:
        """Test floor multiple calculation for sales."""
        assert sample_sale_event.floor_multiple == pytest.approx(2.0)


class TestNFTDelistingEvent:
    """Tests for NFTDelistingEvent model."""

    def test_create_delisting_event(self, sample_delisting_event: NFTDelistingEvent) -> None:
        """Test creating a delisting event."""
        assert sample_delisting_event.token_id == "123"
        assert sample_delisting_event.marketplace == "magic_eden"
        assert sample_delisting_event.original_price_native == Decimal("0.5")


class TestZeroAddress:
    """Tests for zero address constant and detection."""

    def test_zero_address_constant(self) -> None:
        """Test the zero address constant is correct."""
        assert ZERO_ADDRESS == "0x0000000000000000000000000000000000000000"
        assert len(ZERO_ADDRESS) == 42
