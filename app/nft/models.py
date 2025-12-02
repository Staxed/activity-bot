"""Pydantic models for NFT events."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator

# Zero address constant for mint/burn detection
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


def _format_address(address: str) -> str:
    """Format address with checksum removed (lowercase).

    Args:
        address: Ethereum address

    Returns:
        Lowercase address
    """
    return address.lower()


def _short_address(address: str) -> str:
    """Create shortened address for display.

    Args:
        address: Full Ethereum address

    Returns:
        Shortened format (0x1234...5678)
    """
    if len(address) < 12:
        return address
    return f"{address[:6]}...{address[-4:]}"


class NFTMintEvent(BaseModel):
    """NFT mint event from on-chain data.

    Attributes:
        collection_id: Database ID of the collection
        token_id: NFT token ID
        to_address: Address receiving the minted NFT
        chain: Blockchain network (e.g., 'base', 'ethereum')
        token_image_url: NFT image URL (if available)
        price_native: Mint price in native currency (ETH)
        price_usd: Mint price in USD (if available)
        transaction_hash: On-chain transaction hash
        block_number: Block number of the transaction
        event_timestamp: When the mint occurred
    """

    collection_id: int = Field(..., description="Database collection ID")
    token_id: str = Field(..., description="NFT token ID")
    to_address: str = Field(..., description="Minter/recipient address")
    chain: str = Field(default="base", description="Blockchain network")
    token_image_url: str | None = Field(None, description="NFT image URL")
    price_native: Decimal | None = Field(None, description="Mint price in ETH")
    price_usd: Decimal | None = Field(None, description="Mint price in USD")
    transaction_hash: str | None = Field(None, description="Transaction hash")
    block_number: int | None = Field(None, description="Block number")
    event_timestamp: datetime = Field(..., description="Event timestamp")

    @field_validator("to_address", mode="before")
    @classmethod
    def normalize_address(cls, v: str) -> str:
        """Normalize address to lowercase."""
        return _format_address(v)

    @field_validator("event_timestamp", mode="before")
    @classmethod
    def ensure_timezone(cls, v: datetime | str) -> datetime:
        """Ensure timestamp is timezone-aware."""
        if isinstance(v, str):
            v = datetime.fromisoformat(v.replace("Z", "+00:00"))
        if v.tzinfo is None:
            return v.replace(tzinfo=UTC)
        return v

    @property
    def short_to_address(self) -> str:
        """Get shortened to_address for display."""
        return _short_address(self.to_address)

    @classmethod
    def from_thirdweb_webhook(
        cls,
        collection_id: int,
        token_id: str,
        to_address: str,
        transaction_hash: str,
        block_number: int,
        timestamp: datetime,
        chain: str = "base",
        price_native: Decimal | None = None,
        price_usd: Decimal | None = None,
        token_image_url: str | None = None,
    ) -> "NFTMintEvent":
        """Create from Thirdweb Insight webhook data.

        Args:
            collection_id: Database collection ID
            token_id: NFT token ID
            to_address: Minter address
            transaction_hash: Transaction hash
            block_number: Block number
            timestamp: Event timestamp
            chain: Blockchain network
            price_native: Optional mint price in ETH
            price_usd: Optional mint price in USD
            token_image_url: Optional token image URL

        Returns:
            NFTMintEvent instance
        """
        return cls(
            collection_id=collection_id,
            token_id=token_id,
            to_address=to_address,
            chain=chain,
            token_image_url=token_image_url,
            price_native=price_native,
            price_usd=price_usd,
            transaction_hash=transaction_hash,
            block_number=block_number,
            event_timestamp=timestamp,
        )


class NFTTransferEvent(BaseModel):
    """NFT transfer event from on-chain data.

    Attributes:
        collection_id: Database ID of the collection
        token_id: NFT token ID
        from_address: Address sending the NFT
        to_address: Address receiving the NFT
        chain: Blockchain network (e.g., 'base', 'ethereum')
        token_image_url: NFT image URL (if available)
        transaction_hash: On-chain transaction hash
        block_number: Block number of the transaction
        event_timestamp: When the transfer occurred
    """

    collection_id: int = Field(..., description="Database collection ID")
    token_id: str = Field(..., description="NFT token ID")
    from_address: str = Field(..., description="Sender address")
    to_address: str = Field(..., description="Recipient address")
    chain: str = Field(default="base", description="Blockchain network")
    token_image_url: str | None = Field(None, description="NFT image URL")
    transaction_hash: str | None = Field(None, description="Transaction hash")
    block_number: int | None = Field(None, description="Block number")
    event_timestamp: datetime = Field(..., description="Event timestamp")

    @field_validator("from_address", "to_address", mode="before")
    @classmethod
    def normalize_address(cls, v: str) -> str:
        """Normalize address to lowercase."""
        return _format_address(v)

    @field_validator("event_timestamp", mode="before")
    @classmethod
    def ensure_timezone(cls, v: datetime | str) -> datetime:
        """Ensure timestamp is timezone-aware."""
        if isinstance(v, str):
            v = datetime.fromisoformat(v.replace("Z", "+00:00"))
        if v.tzinfo is None:
            return v.replace(tzinfo=UTC)
        return v

    @property
    def short_from_address(self) -> str:
        """Get shortened from_address for display."""
        return _short_address(self.from_address)

    @property
    def short_to_address(self) -> str:
        """Get shortened to_address for display."""
        return _short_address(self.to_address)

    @classmethod
    def from_thirdweb_webhook(
        cls,
        collection_id: int,
        token_id: str,
        from_address: str,
        to_address: str,
        transaction_hash: str,
        block_number: int,
        timestamp: datetime,
        chain: str = "base",
        token_image_url: str | None = None,
    ) -> "NFTTransferEvent":
        """Create from Thirdweb Insight webhook data.

        Args:
            collection_id: Database collection ID
            token_id: NFT token ID
            from_address: Sender address
            to_address: Recipient address
            transaction_hash: Transaction hash
            block_number: Block number
            timestamp: Event timestamp
            chain: Blockchain network
            token_image_url: Optional token image URL

        Returns:
            NFTTransferEvent instance
        """
        return cls(
            collection_id=collection_id,
            token_id=token_id,
            from_address=from_address,
            to_address=to_address,
            chain=chain,
            token_image_url=token_image_url,
            transaction_hash=transaction_hash,
            block_number=block_number,
            event_timestamp=timestamp,
        )


class NFTBurnEvent(BaseModel):
    """NFT burn event from on-chain data.

    Attributes:
        collection_id: Database ID of the collection
        token_id: NFT token ID
        from_address: Address burning the NFT
        chain: Blockchain network (e.g., 'base', 'ethereum')
        token_image_url: NFT image URL (if available)
        transaction_hash: On-chain transaction hash
        block_number: Block number of the transaction
        event_timestamp: When the burn occurred
    """

    collection_id: int = Field(..., description="Database collection ID")
    token_id: str = Field(..., description="NFT token ID")
    from_address: str = Field(..., description="Burner address")
    chain: str = Field(default="base", description="Blockchain network")
    token_image_url: str | None = Field(None, description="NFT image URL")
    transaction_hash: str | None = Field(None, description="Transaction hash")
    block_number: int | None = Field(None, description="Block number")
    event_timestamp: datetime = Field(..., description="Event timestamp")

    @field_validator("from_address", mode="before")
    @classmethod
    def normalize_address(cls, v: str) -> str:
        """Normalize address to lowercase."""
        return _format_address(v)

    @field_validator("event_timestamp", mode="before")
    @classmethod
    def ensure_timezone(cls, v: datetime | str) -> datetime:
        """Ensure timestamp is timezone-aware."""
        if isinstance(v, str):
            v = datetime.fromisoformat(v.replace("Z", "+00:00"))
        if v.tzinfo is None:
            return v.replace(tzinfo=UTC)
        return v

    @property
    def short_from_address(self) -> str:
        """Get shortened from_address for display."""
        return _short_address(self.from_address)

    @classmethod
    def from_thirdweb_webhook(
        cls,
        collection_id: int,
        token_id: str,
        from_address: str,
        transaction_hash: str,
        block_number: int,
        timestamp: datetime,
        chain: str = "base",
        token_image_url: str | None = None,
    ) -> "NFTBurnEvent":
        """Create from Thirdweb Insight webhook data.

        Args:
            collection_id: Database collection ID
            token_id: NFT token ID
            from_address: Burner address
            transaction_hash: Transaction hash
            block_number: Block number
            timestamp: Event timestamp
            chain: Blockchain network
            token_image_url: Optional token image URL

        Returns:
            NFTBurnEvent instance
        """
        return cls(
            collection_id=collection_id,
            token_id=token_id,
            from_address=from_address,
            chain=chain,
            token_image_url=token_image_url,
            transaction_hash=transaction_hash,
            block_number=block_number,
            event_timestamp=timestamp,
        )


class NFTListingEvent(BaseModel):
    """NFT listing event from marketplace.

    Attributes:
        collection_id: Database ID of the collection
        token_id: NFT token ID
        token_name: NFT name (if available)
        token_image_url: NFT image URL (if available)
        seller_address: Seller's address
        marketplace: Marketplace name (magic_eden, opensea, rarible)
        price_native: Listing price in native currency (ETH)
        price_usd: Listing price in USD (if available)
        floor_price_native: Collection floor price at listing time
        rarity_rank: NFT rarity rank (if available)
        listing_id: Marketplace's unique listing ID
        event_timestamp: When the listing was created
    """

    collection_id: int = Field(..., description="Database collection ID")
    token_id: str = Field(..., description="NFT token ID")
    token_name: str | None = Field(None, description="NFT name")
    token_image_url: str | None = Field(None, description="NFT image URL")
    seller_address: str = Field(..., description="Seller address")
    marketplace: str = Field(..., description="Marketplace name")
    price_native: Decimal = Field(..., description="Price in ETH")
    price_usd: Decimal | None = Field(None, description="Price in USD")
    floor_price_native: Decimal | None = Field(None, description="Floor price in ETH")
    rarity_rank: int | None = Field(None, description="Rarity rank")
    listing_id: str = Field(..., description="Marketplace listing ID")
    event_timestamp: datetime = Field(..., description="Event timestamp")
    is_active: bool = Field(True, description="Whether listing is active")

    @field_validator("seller_address", mode="before")
    @classmethod
    def normalize_address(cls, v: str) -> str:
        """Normalize address to lowercase."""
        return _format_address(v)

    @field_validator("event_timestamp", mode="before")
    @classmethod
    def ensure_timezone(cls, v: datetime | str) -> datetime:
        """Ensure timestamp is timezone-aware."""
        if isinstance(v, str):
            v = datetime.fromisoformat(v.replace("Z", "+00:00"))
        if v.tzinfo is None:
            return v.replace(tzinfo=UTC)
        return v

    @property
    def short_seller_address(self) -> str:
        """Get shortened seller_address for display."""
        return _short_address(self.seller_address)

    @property
    def floor_multiple(self) -> float | None:
        """Calculate price as multiple of floor price."""
        if self.floor_price_native and self.floor_price_native > 0:
            return float(self.price_native / self.floor_price_native)
        return None

    @classmethod
    def from_magic_eden_response(
        cls,
        collection_id: int,
        data: dict[str, Any],
        floor_price: Decimal | None = None,
    ) -> "NFTListingEvent":
        """Create from Magic Eden API response.

        Args:
            collection_id: Database collection ID
            data: Magic Eden listing data
            floor_price: Current floor price

        Returns:
            NFTListingEvent instance
        """
        # Parse timestamp - Magic Eden uses Unix timestamp in milliseconds
        timestamp_ms = data.get("createdAt") or data.get("blockTimestamp", 0)
        if isinstance(timestamp_ms, str):
            timestamp = datetime.fromisoformat(timestamp_ms.replace("Z", "+00:00"))
        else:
            timestamp = datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)

        return cls(
            collection_id=collection_id,
            token_id=str(data.get("tokenId", data.get("tokenMint", ""))),
            token_name=data.get("name") or data.get("tokenName"),
            token_image_url=data.get("image") or data.get("imageURI"),
            seller_address=data.get("seller", ""),
            marketplace="magic_eden",
            price_native=Decimal(str(data.get("price", 0))),
            price_usd=Decimal(str(data["priceUsd"])) if data.get("priceUsd") else None,
            floor_price_native=floor_price,
            rarity_rank=data.get("rarity", {}).get("rank") if data.get("rarity") else None,
            listing_id=data.get("id", data.get("signature", "")),
            event_timestamp=timestamp,
        )

    @classmethod
    def from_opensea_response(
        cls,
        collection_id: int,
        data: dict[str, Any],
        floor_price: Decimal | None = None,
    ) -> "NFTListingEvent":
        """Create from OpenSea API response.

        Args:
            collection_id: Database collection ID
            data: OpenSea listing data
            floor_price: Current floor price

        Returns:
            NFTListingEvent instance
        """
        # Parse price from OpenSea format
        price_data = data.get("price", {}).get("current", {})
        price_wei = int(price_data.get("value", 0))
        price_native = Decimal(price_wei) / Decimal("1000000000000000000")  # Wei to ETH

        # Parse timestamp
        timestamp_str = data.get("listing_time") or data.get("created_date", "")
        if timestamp_str:
            timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        else:
            timestamp = datetime.now(UTC)

        nft_data = data.get("nft", {}) or data.get("asset", {})

        return cls(
            collection_id=collection_id,
            token_id=str(nft_data.get("identifier", nft_data.get("token_id", ""))),
            token_name=nft_data.get("name"),
            token_image_url=nft_data.get("image_url"),
            seller_address=data.get("maker", {}).get("address", ""),
            marketplace="opensea",
            price_native=price_native,
            price_usd=Decimal(str(price_data["usd"])) if price_data.get("usd") else None,
            floor_price_native=floor_price,
            rarity_rank=nft_data.get("rarity", {}).get("rank") if nft_data.get("rarity") else None,
            listing_id=data.get("order_hash", ""),
            event_timestamp=timestamp,
        )

    @classmethod
    def from_rarible_response(
        cls,
        collection_id: int,
        data: dict[str, Any],
        floor_price: Decimal | None = None,
    ) -> "NFTListingEvent":
        """Create from Rarible API response.

        Args:
            collection_id: Database collection ID
            data: Rarible listing data
            floor_price: Current floor price

        Returns:
            NFTListingEvent instance
        """
        # Parse price from Rarible format
        make_price = data.get("make", {}).get("value", data.get("makePrice", "0"))
        price_native = Decimal(str(make_price))

        # Parse timestamp
        timestamp_str = data.get("createdAt") or data.get("date", "")
        if timestamp_str:
            timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        else:
            timestamp = datetime.now(UTC)

        # Extract token info from itemId (format: "ETHEREUM:contract:tokenId")
        item_id = data.get("itemId", "")
        token_id = item_id.split(":")[-1] if ":" in item_id else item_id

        return cls(
            collection_id=collection_id,
            token_id=token_id,
            token_name=data.get("meta", {}).get("name"),
            token_image_url=data.get("meta", {}).get("content", [{}])[0].get("url")
            if data.get("meta", {}).get("content")
            else None,
            seller_address=data.get("maker", "").split(":")[-1] if data.get("maker") else "",
            marketplace="rarible",
            price_native=price_native,
            price_usd=Decimal(str(data["makePriceUsd"])) if data.get("makePriceUsd") else None,
            floor_price_native=floor_price,
            rarity_rank=None,  # Rarible doesn't provide rarity in listings
            listing_id=data.get("id", data.get("hash", "")),
            event_timestamp=timestamp,
        )


class NFTSaleEvent(BaseModel):
    """NFT sale event from marketplace.

    Attributes:
        collection_id: Database ID of the collection
        token_id: NFT token ID
        token_name: NFT name (if available)
        token_image_url: NFT image URL (if available)
        seller_address: Seller's address
        buyer_address: Buyer's address
        marketplace: Marketplace name (magic_eden, opensea, rarible)
        price_native: Sale price in native currency (ETH)
        price_usd: Sale price in USD (if available)
        floor_price_native: Collection floor price at sale time
        rarity_rank: NFT rarity rank (if available)
        sale_id: Marketplace's unique sale/transaction ID
        event_timestamp: When the sale occurred
    """

    collection_id: int = Field(..., description="Database collection ID")
    token_id: str = Field(..., description="NFT token ID")
    token_name: str | None = Field(None, description="NFT name")
    token_image_url: str | None = Field(None, description="NFT image URL")
    seller_address: str = Field(..., description="Seller address")
    buyer_address: str = Field(..., description="Buyer address")
    marketplace: str = Field(..., description="Marketplace name")
    price_native: Decimal = Field(..., description="Price in ETH")
    price_usd: Decimal | None = Field(None, description="Price in USD")
    floor_price_native: Decimal | None = Field(None, description="Floor price in ETH")
    rarity_rank: int | None = Field(None, description="Rarity rank")
    sale_id: str = Field(..., description="Marketplace sale ID")
    event_timestamp: datetime = Field(..., description="Event timestamp")

    @field_validator("seller_address", "buyer_address", mode="before")
    @classmethod
    def normalize_address(cls, v: str) -> str:
        """Normalize address to lowercase."""
        return _format_address(v)

    @field_validator("event_timestamp", mode="before")
    @classmethod
    def ensure_timezone(cls, v: datetime | str) -> datetime:
        """Ensure timestamp is timezone-aware."""
        if isinstance(v, str):
            v = datetime.fromisoformat(v.replace("Z", "+00:00"))
        if v.tzinfo is None:
            return v.replace(tzinfo=UTC)
        return v

    @property
    def short_seller_address(self) -> str:
        """Get shortened seller_address for display."""
        return _short_address(self.seller_address)

    @property
    def short_buyer_address(self) -> str:
        """Get shortened buyer_address for display."""
        return _short_address(self.buyer_address)

    @property
    def floor_multiple(self) -> float | None:
        """Calculate price as multiple of floor price."""
        if self.floor_price_native and self.floor_price_native > 0:
            return float(self.price_native / self.floor_price_native)
        return None

    @classmethod
    def from_magic_eden_response(
        cls,
        collection_id: int,
        data: dict[str, Any],
        floor_price: Decimal | None = None,
    ) -> "NFTSaleEvent":
        """Create from Magic Eden API response.

        Args:
            collection_id: Database collection ID
            data: Magic Eden sale data
            floor_price: Current floor price

        Returns:
            NFTSaleEvent instance
        """
        # Parse timestamp
        timestamp_ms = data.get("blockTimestamp") or data.get("createdAt", 0)
        if isinstance(timestamp_ms, str):
            timestamp = datetime.fromisoformat(timestamp_ms.replace("Z", "+00:00"))
        else:
            timestamp = datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)

        return cls(
            collection_id=collection_id,
            token_id=str(data.get("tokenId", data.get("tokenMint", ""))),
            token_name=data.get("name") or data.get("tokenName"),
            token_image_url=data.get("image") or data.get("imageURI"),
            seller_address=data.get("seller", ""),
            buyer_address=data.get("buyer", ""),
            marketplace="magic_eden",
            price_native=Decimal(str(data.get("price", 0))),
            price_usd=Decimal(str(data["priceUsd"])) if data.get("priceUsd") else None,
            floor_price_native=floor_price,
            rarity_rank=data.get("rarity", {}).get("rank") if data.get("rarity") else None,
            sale_id=data.get("signature", data.get("txId", "")),
            event_timestamp=timestamp,
        )

    @classmethod
    def from_opensea_response(
        cls,
        collection_id: int,
        data: dict[str, Any],
        floor_price: Decimal | None = None,
    ) -> "NFTSaleEvent":
        """Create from OpenSea API response.

        Args:
            collection_id: Database collection ID
            data: OpenSea sale data
            floor_price: Current floor price

        Returns:
            NFTSaleEvent instance
        """
        # Parse price
        payment = data.get("payment", {})
        price_wei = int(payment.get("quantity", 0))
        price_native = Decimal(price_wei) / Decimal("1000000000000000000")

        # Parse timestamp
        timestamp_str = data.get("event_timestamp") or data.get("closing_date", "")
        if timestamp_str:
            timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        else:
            timestamp = datetime.now(UTC)

        nft_data = data.get("nft", {}) or data.get("asset", {})

        return cls(
            collection_id=collection_id,
            token_id=str(nft_data.get("identifier", nft_data.get("token_id", ""))),
            token_name=nft_data.get("name"),
            token_image_url=nft_data.get("image_url"),
            seller_address=data.get("seller", ""),
            buyer_address=data.get("buyer", data.get("winner_account", {}).get("address", "")),
            marketplace="opensea",
            price_native=price_native,
            price_usd=Decimal(str(payment["usd_price"])) if payment.get("usd_price") else None,
            floor_price_native=floor_price,
            rarity_rank=nft_data.get("rarity", {}).get("rank") if nft_data.get("rarity") else None,
            sale_id=data.get("transaction", {}).get("hash", data.get("order_hash", "")),
            event_timestamp=timestamp,
        )

    @classmethod
    def from_rarible_response(
        cls,
        collection_id: int,
        data: dict[str, Any],
        floor_price: Decimal | None = None,
    ) -> "NFTSaleEvent":
        """Create from Rarible API response.

        Args:
            collection_id: Database collection ID
            data: Rarible sale data
            floor_price: Current floor price

        Returns:
            NFTSaleEvent instance
        """
        # Parse price
        take_price = data.get("take", {}).get("value", data.get("price", "0"))
        price_native = Decimal(str(take_price))

        # Parse timestamp
        timestamp_str = data.get("date", "")
        if timestamp_str:
            timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        else:
            timestamp = datetime.now(UTC)

        # Extract token info
        item_id = data.get("itemId", "")
        token_id = item_id.split(":")[-1] if ":" in item_id else item_id

        return cls(
            collection_id=collection_id,
            token_id=token_id,
            token_name=data.get("nft", {}).get("meta", {}).get("name"),
            token_image_url=None,
            seller_address=data.get("seller", "").split(":")[-1] if data.get("seller") else "",
            buyer_address=data.get("buyer", "").split(":")[-1] if data.get("buyer") else "",
            marketplace="rarible",
            price_native=price_native,
            price_usd=Decimal(str(data["priceUsd"])) if data.get("priceUsd") else None,
            floor_price_native=floor_price,
            rarity_rank=None,
            sale_id=data.get("id", data.get("transactionHash", "")),
            event_timestamp=timestamp,
        )


class NFTDelistingEvent(BaseModel):
    """NFT delisting (cancelled listing) event from marketplace.

    Attributes:
        collection_id: Database ID of the collection
        token_id: NFT token ID
        token_name: NFT name (if available)
        token_image_url: Token image URL (if available)
        seller_address: Seller's address
        marketplace: Marketplace name
        original_price_native: Price it was listed at
        delisting_id: Unique ID for this delisting event
        event_timestamp: When the delisting occurred
    """

    collection_id: int = Field(..., description="Database collection ID")
    token_id: str = Field(..., description="NFT token ID")
    token_name: str | None = Field(None, description="NFT name")
    token_image_url: str | None = Field(None, description="Token image URL")
    seller_address: str = Field(..., description="Seller address")
    marketplace: str = Field(..., description="Marketplace name")
    original_price_native: Decimal | None = Field(None, description="Original listing price")
    delisting_id: str = Field(..., description="Delisting event ID")
    event_timestamp: datetime = Field(..., description="Event timestamp")

    @field_validator("seller_address", mode="before")
    @classmethod
    def normalize_address(cls, v: str) -> str:
        """Normalize address to lowercase."""
        return _format_address(v)

    @field_validator("event_timestamp", mode="before")
    @classmethod
    def ensure_timezone(cls, v: datetime | str) -> datetime:
        """Ensure timestamp is timezone-aware."""
        if isinstance(v, str):
            v = datetime.fromisoformat(v.replace("Z", "+00:00"))
        if v.tzinfo is None:
            return v.replace(tzinfo=UTC)
        return v

    @property
    def short_seller_address(self) -> str:
        """Get shortened seller_address for display."""
        return _short_address(self.seller_address)
