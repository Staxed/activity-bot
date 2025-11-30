"""Magic Eden API client for NFT marketplace data."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import aiohttp

from app.core.logging import get_logger
from app.nft.marketplaces.base import APIError, MarketplaceClient, RateLimitError
from app.nft.models import NFTDelistingEvent, NFTListingEvent, NFTSaleEvent

logger = get_logger(__name__)

# Magic Eden API base URLs by chain
BASE_URLS = {
    "base": "https://api-mainnet.magiceden.dev/v3/rtp/base",
    "ethereum": "https://api-mainnet.magiceden.dev/v3/rtp/ethereum",
    "polygon": "https://api-mainnet.magiceden.dev/v3/rtp/polygon",
}


class MagicEdenClient(MarketplaceClient):
    """Magic Eden API client.

    Fetches listing and sale data from Magic Eden's Reservoir-based API.
    """

    def __init__(self, api_key: str | None = None) -> None:
        """Initialize Magic Eden client.

        Args:
            api_key: Optional API key for higher rate limits
        """
        self.api_key = api_key
        self.session: aiohttp.ClientSession | None = None

    @property
    def name(self) -> str:
        """Get marketplace name."""
        return "magic_eden"

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
                headers["Authorization"] = f"Bearer {self.api_key}"
            self.session = aiohttp.ClientSession(headers=headers)
        return self.session

    def _get_base_url(self, chain: str) -> str:
        """Get base URL for chain.

        Args:
            chain: Blockchain network

        Returns:
            Base URL for the chain

        Raises:
            ValueError: If chain is not supported
        """
        chain_lower = chain.lower()
        if chain_lower not in BASE_URLS:
            raise ValueError(f"Chain {chain} not supported by Magic Eden")
        return BASE_URLS[chain_lower]

    async def _request(
        self,
        chain: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make API request.

        Args:
            chain: Blockchain network
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            JSON response data

        Raises:
            RateLimitError: If rate limited
            APIError: If API returns error
        """
        session = await self._ensure_session()
        base_url = self._get_base_url(chain)
        url = f"{base_url}{endpoint}"

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
            logger.error("magiceden.request.failed", url=url, error=str(e))
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
            logger.warning("magiceden.listings.no_collection_id")
            return []

        # Get floor price first
        floor_price = await self.get_floor_price(contract_address, chain)

        params: dict[str, Any] = {
            "collection": contract_address.lower(),
            "sortBy": "createdAt",
            "sortDirection": "desc",
            "limit": 50,
        }

        if since:
            # Magic Eden uses Unix timestamp
            params["startTimestamp"] = int(since.timestamp())

        try:
            data = await self._request(chain, "/orders/asks/v5", params)
        except (RateLimitError, APIError) as e:
            logger.error("magiceden.listings.failed", error=str(e))
            return []

        orders = data.get("orders", [])
        listings: list[NFTListingEvent] = []

        for order in orders:
            try:
                # Extract token info
                criteria = order.get("criteria", {}).get("data", {})
                token_info = criteria.get("token", {})

                # Parse timestamp
                created_at = order.get("createdAt")
                if created_at:
                    timestamp = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                else:
                    timestamp = datetime.now(UTC)

                # Skip if before since timestamp
                if since and timestamp < since:
                    continue

                # Parse price (in native currency)
                price_native = Decimal(
                    str(order.get("price", {}).get("amount", {}).get("decimal", 0))
                )
                price_usd_str = order.get("price", {}).get("amount", {}).get("usd")
                price_usd = Decimal(str(price_usd_str)) if price_usd_str else None

                listing = NFTListingEvent(
                    collection_id=collection_db_id,
                    token_id=str(token_info.get("tokenId", criteria.get("tokenId", ""))),
                    token_name=token_info.get("name"),
                    token_image_url=token_info.get("image"),
                    seller_address=order.get("maker", ""),
                    marketplace="magic_eden",
                    price_native=price_native,
                    price_usd=price_usd,
                    floor_price_native=floor_price,
                    rarity_rank=token_info.get("rarityRank"),
                    listing_id=order.get("id", ""),
                    event_timestamp=timestamp,
                    is_active=order.get("status") == "active",
                )
                listings.append(listing)

            except Exception as e:
                logger.warning("magiceden.listing.parse_failed", error=str(e))
                continue

        logger.info(
            "magiceden.listings.fetched", count=len(listings), contract=contract_address[:10]
        )
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
            logger.warning("magiceden.sales.no_collection_id")
            return []

        # Get floor price
        floor_price = await self.get_floor_price(contract_address, chain)

        params: dict[str, Any] = {
            "collection": contract_address.lower(),
            "limit": 50,
        }

        if since:
            params["startTimestamp"] = int(since.timestamp())

        try:
            data = await self._request(chain, "/sales/v6", params)
        except (RateLimitError, APIError) as e:
            logger.error("magiceden.sales.failed", error=str(e))
            return []

        sales_data = data.get("sales", [])
        sales: list[NFTSaleEvent] = []

        for sale in sales_data:
            try:
                # Parse timestamp
                timestamp_val = sale.get("timestamp")
                if isinstance(timestamp_val, int):
                    timestamp = datetime.fromtimestamp(timestamp_val, tz=UTC)
                elif isinstance(timestamp_val, str):
                    timestamp = datetime.fromisoformat(timestamp_val.replace("Z", "+00:00"))
                else:
                    timestamp = datetime.now(UTC)

                # Skip if before since timestamp
                if since and timestamp < since:
                    continue

                # Parse price
                price_data = sale.get("price", {})
                price_native = Decimal(str(price_data.get("amount", {}).get("decimal", 0)))
                price_usd_str = price_data.get("amount", {}).get("usd")
                price_usd = Decimal(str(price_usd_str)) if price_usd_str else None

                token_info = sale.get("token", {})

                sale_event = NFTSaleEvent(
                    collection_id=collection_db_id,
                    token_id=str(token_info.get("tokenId", "")),
                    token_name=token_info.get("name"),
                    token_image_url=token_info.get("image"),
                    seller_address=sale.get("from", ""),
                    buyer_address=sale.get("to", ""),
                    marketplace="magic_eden",
                    price_native=price_native,
                    price_usd=price_usd,
                    floor_price_native=floor_price,
                    rarity_rank=token_info.get("rarityRank"),
                    sale_id=sale.get("txHash", sale.get("id", "")),
                    event_timestamp=timestamp,
                )
                sales.append(sale_event)

            except Exception as e:
                logger.warning("magiceden.sale.parse_failed", error=str(e))
                continue

        logger.info("magiceden.sales.fetched", count=len(sales), contract=contract_address[:10])
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
        params = {"id": contract_address.lower()}

        try:
            data = await self._request(chain, "/collections/v7", params)
        except (RateLimitError, APIError) as e:
            logger.warning("magiceden.floor.failed", error=str(e))
            return None

        collections = data.get("collections", [])
        if not collections:
            return None

        floor_ask = collections[0].get("floorAsk", {})
        price = floor_ask.get("price", {}).get("amount", {}).get("decimal")

        if price is not None:
            return Decimal(str(price))
        return None

    async def get_delistings(
        self,
        contract_address: str,
        chain: str,
        since: datetime | None = None,
        collection_db_id: int | None = None,
    ) -> list[NFTDelistingEvent]:
        """Fetch cancelled listings.

        Magic Eden API may not expose this directly - check for listings
        that have become inactive.

        Args:
            contract_address: NFT contract address
            chain: Blockchain network
            since: Only fetch delistings after this timestamp
            collection_db_id: Database ID of the collection

        Returns:
            List of NFTDelistingEvent objects
        """
        # Magic Eden doesn't have a direct delistings endpoint
        # We would need to track listing state changes
        return []

    async def close(self) -> None:
        """Close the HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None
