"""OpenSea API client for NFT marketplace data."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import aiohttp

from app.core.logging import get_logger
from app.nft.marketplaces.base import APIError, MarketplaceClient, RateLimitError
from app.nft.models import NFTListingEvent, NFTSaleEvent

logger = get_logger(__name__)

# OpenSea API base URL
BASE_URL = "https://api.opensea.io/api/v2"

# Chain name mapping for OpenSea
CHAIN_MAPPING = {
    "base": "base",
    "ethereum": "ethereum",
    "polygon": "matic",
    "arbitrum": "arbitrum",
    "optimism": "optimism",
}


class OpenSeaClient(MarketplaceClient):
    """OpenSea API client.

    Fetches listing and sale data from OpenSea's API.
    Requires an API key for access.
    """

    def __init__(self, api_key: str) -> None:
        """Initialize OpenSea client.

        Args:
            api_key: OpenSea API key (required)
        """
        self.api_key = api_key
        self.session: aiohttp.ClientSession | None = None

    @property
    def name(self) -> str:
        """Get marketplace name."""
        return "opensea"

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Ensure aiohttp session exists.

        Returns:
            Active aiohttp session
        """
        if self.session is None or self.session.closed:
            headers = {
                "Accept": "application/json",
                "X-API-KEY": self.api_key,
            }
            self.session = aiohttp.ClientSession(headers=headers)
        return self.session

    def _get_chain_name(self, chain: str) -> str:
        """Map chain name to OpenSea format.

        Args:
            chain: Our chain name

        Returns:
            OpenSea chain name

        Raises:
            ValueError: If chain not supported
        """
        chain_lower = chain.lower()
        if chain_lower not in CHAIN_MAPPING:
            raise ValueError(f"Chain {chain} not supported by OpenSea")
        return CHAIN_MAPPING[chain_lower]

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

                if response.status == 401:
                    raise APIError(401, "Invalid API key")

                if response.status != 200:
                    text = await response.text()
                    raise APIError(response.status, text[:200])

                return await response.json()  # type: ignore[no-any-return]

        except aiohttp.ClientError as e:
            logger.error("opensea.request.failed", url=url, error=str(e))
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
            logger.warning("opensea.listings.no_collection_id")
            return []

        os_chain = self._get_chain_name(chain)

        # Get floor price first
        floor_price = await self.get_floor_price(contract_address, chain)

        # OpenSea uses collection slug or contract address
        # Using the listings endpoint with contract filter
        params: dict[str, Any] = {
            "asset_contract_address": contract_address.lower(),
            "limit": 50,
        }

        try:
            data = await self._request(f"/orders/{os_chain}/seaport/listings", params)
        except (RateLimitError, APIError) as e:
            logger.error("opensea.listings.failed", error=str(e))
            return []

        orders = data.get("orders", [])
        listings: list[NFTListingEvent] = []

        for order in orders:
            try:
                # Parse timestamp
                listing_time = order.get("listing_time")
                if listing_time:
                    timestamp = datetime.fromtimestamp(listing_time, tz=UTC)
                else:
                    created_date = order.get("created_date", "")
                    if created_date:
                        timestamp = datetime.fromisoformat(created_date.replace("Z", "+00:00"))
                    else:
                        timestamp = datetime.now(UTC)

                # Skip if before since timestamp
                if since and timestamp < since:
                    continue

                # Parse price from protocol_data
                protocol_data = order.get("protocol_data", {})
                offer = protocol_data.get("parameters", {}).get("offer", [{}])[0]
                start_amount = int(offer.get("startAmount", 0))
                price_native = Decimal(start_amount) / Decimal("1000000000000000000")

                # Get maker NFT details
                maker_asset = order.get("maker_asset_bundle", {}).get("assets", [{}])[0]

                listing = NFTListingEvent(
                    collection_id=collection_db_id,
                    token_id=str(maker_asset.get("token_id", "")),
                    token_name=maker_asset.get("name"),
                    token_image_url=maker_asset.get("image_url"),
                    seller_address=order.get("maker", {}).get("address", ""),
                    marketplace="opensea",
                    price_native=price_native,
                    price_usd=None,  # OpenSea doesn't provide USD in listing response
                    floor_price_native=floor_price,
                    rarity_rank=maker_asset.get("traits", {}).get("rank"),
                    listing_id=order.get("order_hash", ""),
                    event_timestamp=timestamp,
                    is_active=not order.get("cancelled", False)
                    and not order.get("finalized", False),
                )
                listings.append(listing)

            except Exception as e:
                logger.warning("opensea.listing.parse_failed", error=str(e))
                continue

        logger.info("opensea.listings.fetched", count=len(listings), contract=contract_address[:10])
        return listings

    async def get_sales(
        self,
        contract_address: str,
        chain: str,
        since: datetime | None = None,
        collection_db_id: int | None = None,
    ) -> list[NFTSaleEvent]:
        """Fetch sales for a collection.

        Uses the events endpoint with event_type=sale filter.

        Args:
            contract_address: NFT contract address
            chain: Blockchain network
            since: Only fetch sales after this timestamp
            collection_db_id: Database ID of the collection

        Returns:
            List of NFTSaleEvent objects
        """
        if collection_db_id is None:
            logger.warning("opensea.sales.no_collection_id")
            return []

        os_chain = self._get_chain_name(chain)

        # Get floor price
        floor_price = await self.get_floor_price(contract_address, chain)

        params: dict[str, Any] = {
            "event_type": "sale",
            "limit": 50,
        }

        if since:
            params["after"] = int(since.timestamp())

        try:
            # Use events endpoint for the specific contract
            data = await self._request(
                f"/events/chain/{os_chain}/contract/{contract_address.lower()}",
                params,
            )
        except (RateLimitError, APIError) as e:
            logger.error("opensea.sales.failed", error=str(e))
            return []

        events = data.get("asset_events", [])
        sales: list[NFTSaleEvent] = []

        for event in events:
            try:
                if event.get("event_type") != "sale":
                    continue

                # Parse timestamp
                event_timestamp = event.get("event_timestamp")
                if event_timestamp:
                    timestamp = datetime.fromisoformat(event_timestamp.replace("Z", "+00:00"))
                else:
                    timestamp = datetime.now(UTC)

                # Skip if before since timestamp
                if since and timestamp < since:
                    continue

                # Parse price
                payment = event.get("payment", {})
                quantity = int(payment.get("quantity", 0))
                price_native = Decimal(quantity) / Decimal("1000000000000000000")
                price_usd_str = payment.get("usd_price")
                price_usd = Decimal(str(price_usd_str)) if price_usd_str else None

                nft = event.get("nft", {})
                tx = event.get("transaction", {})

                sale = NFTSaleEvent(
                    collection_id=collection_db_id,
                    token_id=str(nft.get("identifier", "")),
                    token_name=nft.get("name"),
                    token_image_url=nft.get("image_url"),
                    seller_address=event.get("seller", ""),
                    buyer_address=event.get("buyer", ""),
                    marketplace="opensea",
                    price_native=price_native,
                    price_usd=price_usd,
                    floor_price_native=floor_price,
                    rarity_rank=None,
                    sale_id=tx.get("hash", event.get("order_hash", "")),
                    event_timestamp=timestamp,
                )
                sales.append(sale)

            except Exception as e:
                logger.warning("opensea.sale.parse_failed", error=str(e))
                continue

        logger.info("opensea.sales.fetched", count=len(sales), contract=contract_address[:10])
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
        os_chain = self._get_chain_name(chain)

        try:
            data = await self._request(
                f"/chain/{os_chain}/contract/{contract_address.lower()}/nfts",
                {"limit": 1},
            )
        except (RateLimitError, APIError) as e:
            logger.warning("opensea.floor.failed", error=str(e))
            return None

        # Try to get floor from collection stats
        try:
            # Alternative: use collection endpoint for stats
            collection_data = await self._request(
                f"/chain/{os_chain}/contract/{contract_address.lower()}",
            )
            stats = collection_data.get("collection", {}).get("stats", {})
            floor = stats.get("floor_price")
            if floor is not None:
                return Decimal(str(floor))
        except (RateLimitError, APIError):
            pass

        return None

    async def close(self) -> None:
        """Close the HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None
