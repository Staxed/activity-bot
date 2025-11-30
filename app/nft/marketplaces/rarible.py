"""Rarible API client for NFT marketplace data."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import aiohttp

from app.core.logging import get_logger
from app.nft.marketplaces.base import APIError, MarketplaceClient, RateLimitError
from app.nft.models import NFTListingEvent, NFTSaleEvent

logger = get_logger(__name__)

# Rarible API base URL
BASE_URL = "https://api.rarible.org/v0.1"

# Blockchain name mapping for Rarible
BLOCKCHAIN_MAPPING = {
    "base": "BASE",
    "ethereum": "ETHEREUM",
    "polygon": "POLYGON",
}


class RaribleClient(MarketplaceClient):
    """Rarible API client.

    Fetches listing and sale data from Rarible's public API.
    """

    def __init__(self, api_key: str | None = None) -> None:
        """Initialize Rarible client.

        Args:
            api_key: Optional API key for higher rate limits
        """
        self.api_key = api_key
        self.session: aiohttp.ClientSession | None = None

    @property
    def name(self) -> str:
        """Get marketplace name."""
        return "rarible"

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Ensure aiohttp session exists.

        Returns:
            Active aiohttp session
        """
        if self.session is None or self.session.closed:
            headers = {
                "Accept": "application/json",
            }
            if self.api_key:
                headers["X-API-KEY"] = self.api_key
            self.session = aiohttp.ClientSession(headers=headers)
        return self.session

    def _get_blockchain(self, chain: str) -> str:
        """Map chain name to Rarible blockchain format.

        Args:
            chain: Our chain name

        Returns:
            Rarible blockchain name

        Raises:
            ValueError: If chain not supported
        """
        chain_lower = chain.lower()
        if chain_lower not in BLOCKCHAIN_MAPPING:
            raise ValueError(f"Chain {chain} not supported by Rarible")
        return BLOCKCHAIN_MAPPING[chain_lower]

    def _format_item_id(self, chain: str, contract_address: str, token_id: str = "") -> str:
        """Format item ID in Rarible format.

        Args:
            chain: Blockchain network
            contract_address: Contract address
            token_id: Optional token ID

        Returns:
            Rarible-formatted item ID
        """
        blockchain = self._get_blockchain(chain)
        if token_id:
            return f"{blockchain}:{contract_address.lower()}:{token_id}"
        return f"{blockchain}:{contract_address.lower()}"

    async def _request(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make API request.

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            JSON response data

        Raises:
            RateLimitError: If rate limited
            APIError: If API returns error
        """
        session = await self._ensure_session()
        url = f"{BASE_URL}{endpoint}"

        try:
            async with session.get(url, params=params) as response:
                if response.status == 429:
                    retry_after = response.headers.get("Retry-After")
                    raise RateLimitError(int(retry_after) if retry_after else 60)

                if response.status != 200:
                    text = await response.text()
                    raise APIError(response.status, text[:200])

                return await response.json()  # type: ignore[no-any-return]

        except aiohttp.ClientError as e:
            logger.error("rarible.request.failed", url=url, error=str(e))
            raise APIError(0, str(e)) from e

    async def get_listings(
        self,
        contract_address: str,
        chain: str,
        since: datetime | None = None,
        collection_db_id: int | None = None,
    ) -> list[NFTListingEvent]:
        """Fetch active listings for a collection.

        Args:
            contract_address: NFT contract address
            chain: Blockchain network
            since: Only fetch listings after this timestamp
            collection_db_id: Database ID of the collection

        Returns:
            List of NFTListingEvent objects
        """
        if collection_db_id is None:
            logger.warning("rarible.listings.no_collection_id")
            return []

        blockchain = self._get_blockchain(chain)
        collection_id = f"{blockchain}:{contract_address.lower()}"

        # Get floor price first
        floor_price = await self.get_floor_price(contract_address, chain)

        params: dict[str, Any] = {
            "size": 50,
            "sort": "LAST_UPDATE_DESC",
            "status": ["ACTIVE"],
        }

        try:
            data = await self._request(
                f"/orders/sell/byCollection", {"collection": collection_id, **params}
            )
        except (RateLimitError, APIError) as e:
            logger.error("rarible.listings.failed", error=str(e))
            return []

        orders = data.get("orders", [])
        listings: list[NFTListingEvent] = []

        for order in orders:
            try:
                # Parse timestamp
                created_at = order.get("createdAt")
                if created_at:
                    timestamp = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                else:
                    timestamp = datetime.now(UTC)

                # Skip if before since timestamp
                if since and timestamp < since:
                    continue

                # Parse price - Rarible uses make/take format
                make_price = order.get("makePrice") or order.get("make", {}).get("value", "0")
                price_native = Decimal(str(make_price))
                price_usd_str = order.get("makePriceUsd")
                price_usd = Decimal(str(price_usd_str)) if price_usd_str else None

                # Extract token info from make asset
                make_asset = order.get("make", {})
                item_id = make_asset.get("type", {}).get("itemId", "")
                token_id = item_id.split(":")[-1] if ":" in item_id else ""

                # Get NFT metadata if available
                nft_meta = order.get("nft", {}).get("meta", {})

                listing = NFTListingEvent(
                    collection_id=collection_db_id,
                    token_id=token_id,
                    token_name=nft_meta.get("name"),
                    token_image_url=nft_meta.get("content", [{}])[0].get("url")
                    if nft_meta.get("content")
                    else None,
                    seller_address=order.get("maker", "").split(":")[-1]
                    if order.get("maker")
                    else "",
                    marketplace="rarible",
                    price_native=price_native,
                    price_usd=price_usd,
                    floor_price_native=floor_price,
                    rarity_rank=None,  # Rarible doesn't expose rarity in listings
                    listing_id=order.get("id", order.get("hash", "")),
                    event_timestamp=timestamp,
                    is_active=order.get("status") == "ACTIVE",
                )
                listings.append(listing)

            except Exception as e:
                logger.warning("rarible.listing.parse_failed", error=str(e))
                continue

        logger.info("rarible.listings.fetched", count=len(listings), contract=contract_address[:10])
        return listings

    async def get_sales(
        self,
        contract_address: str,
        chain: str,
        since: datetime | None = None,
        collection_db_id: int | None = None,
    ) -> list[NFTSaleEvent]:
        """Fetch sales for a collection.

        Args:
            contract_address: NFT contract address
            chain: Blockchain network
            since: Only fetch sales after this timestamp
            collection_db_id: Database ID of the collection

        Returns:
            List of NFTSaleEvent objects
        """
        if collection_db_id is None:
            logger.warning("rarible.sales.no_collection_id")
            return []

        blockchain = self._get_blockchain(chain)
        collection_id = f"{blockchain}:{contract_address.lower()}"

        # Get floor price
        floor_price = await self.get_floor_price(contract_address, chain)

        params: dict[str, Any] = {
            "size": 50,
            "type": ["SELL"],
        }

        try:
            data = await self._request(
                f"/activities/byCollection",
                {"collection": collection_id, **params},
            )
        except (RateLimitError, APIError) as e:
            logger.error("rarible.sales.failed", error=str(e))
            return []

        activities = data.get("activities", [])
        sales: list[NFTSaleEvent] = []

        for activity in activities:
            try:
                if activity.get("@type") != "SELL":
                    continue

                # Parse timestamp
                date_str = activity.get("date")
                if date_str:
                    timestamp = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                else:
                    timestamp = datetime.now(UTC)

                # Skip if before since timestamp
                if since and timestamp < since:
                    continue

                # Parse price
                price_str = activity.get("price", "0")
                price_native = Decimal(str(price_str))
                price_usd_str = activity.get("priceUsd")
                price_usd = Decimal(str(price_usd_str)) if price_usd_str else None

                # Extract token info
                nft = activity.get("nft", {})
                item_id = nft.get("id", "")
                token_id = item_id.split(":")[-1] if ":" in item_id else ""
                nft_meta = nft.get("meta", {})

                # Parse addresses
                seller = activity.get("seller", "")
                buyer = activity.get("buyer", "")
                if ":" in seller:
                    seller = seller.split(":")[-1]
                if ":" in buyer:
                    buyer = buyer.split(":")[-1]

                sale = NFTSaleEvent(
                    collection_id=collection_db_id,
                    token_id=token_id,
                    token_name=nft_meta.get("name"),
                    token_image_url=nft_meta.get("content", [{}])[0].get("url")
                    if nft_meta.get("content")
                    else None,
                    seller_address=seller,
                    buyer_address=buyer,
                    marketplace="rarible",
                    price_native=price_native,
                    price_usd=price_usd,
                    floor_price_native=floor_price,
                    rarity_rank=None,
                    sale_id=activity.get("id", activity.get("transactionHash", "")),
                    event_timestamp=timestamp,
                )
                sales.append(sale)

            except Exception as e:
                logger.warning("rarible.sale.parse_failed", error=str(e))
                continue

        logger.info("rarible.sales.fetched", count=len(sales), contract=contract_address[:10])
        return sales

    async def get_floor_price(
        self,
        contract_address: str,
        chain: str,
    ) -> Decimal | None:
        """Get current floor price for a collection.

        Args:
            contract_address: NFT contract address
            chain: Blockchain network

        Returns:
            Floor price in ETH, or None if unavailable
        """
        blockchain = self._get_blockchain(chain)
        collection_id = f"{blockchain}:{contract_address.lower()}"

        try:
            data = await self._request(f"/collections/{collection_id}/stats")
        except (RateLimitError, APIError) as e:
            logger.warning("rarible.floor.failed", error=str(e))
            return None

        floor = data.get("floorPrice")
        if floor is not None:
            return Decimal(str(floor))
        return None

    async def close(self) -> None:
        """Close the HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None
