"""Magic Eden API client for NFT marketplace data."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import aiohttp

from app.core.logging import get_logger
from app.nft.marketplaces.base import APIError, MarketplaceClient, RateLimitError
from app.nft.models import NFTDelistingEvent, NFTListingEvent, NFTSaleEvent

logger = get_logger(__name__)

# Magic Eden v4 EVM API
BASE_URL = "https://api-mainnet.magiceden.dev/v4/evm-public"

# Supported chains in v4 API
SUPPORTED_CHAINS = {
    "base",
    "ethereum",
    "abstract",
    "apechain",
    "arbitrum",
    "berachain",
    "bsc",
    "polygon",
    "sei",
    "avalanche",
    "monad",
}


class MagicEdenClient(MarketplaceClient):
    """Magic Eden API client.

    Fetches listing and sale data from Magic Eden's v4 EVM API.
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
                "Accept": "*/*",
            }
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self.session = aiohttp.ClientSession(headers=headers)
        return self.session

    def _validate_chain(self, chain: str) -> str:
        """Validate chain is supported.

        Args:
            chain: Blockchain network

        Returns:
            Lowercase chain name

        Raises:
            ValueError: If chain is not supported
        """
        chain_lower = chain.lower()
        if chain_lower not in SUPPORTED_CHAINS:
            raise ValueError(f"Chain {chain} not supported by Magic Eden")
        return chain_lower

    async def _request(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
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

                return await response.json()

        except aiohttp.ClientError as e:
            logger.error("magiceden.request.failed", url=url, error=str(e))
            raise APIError(0, str(e)) from e

    async def get_listings(
        self,
        contract_address: str,
        chain: str,
        since: datetime | None = None,
        collection_db_id: int | None = None,
        collection_slug: str | None = None,
    ) -> list[NFTListingEvent]:
        """Fetch active listings for a collection.

        Args:
            contract_address: NFT contract address
            chain: Blockchain network
            since: Only fetch listings after this timestamp
            collection_db_id: Database ID of the collection
            collection_slug: Collection slug (not used by Magic Eden, uses contract address)

        Returns:
            List of NFTListingEvent objects
        """
        if collection_db_id is None:
            logger.warning("magiceden.listings.no_collection_id")
            return []

        chain_lower = self._validate_chain(chain)

        params: dict[str, Any] = {
            "chain": chain_lower,
            "collectionId": contract_address.lower(),
            "sortBy": "createdAt",
            "sortDir": "desc",
            "limit": 50,
            "status[]": "active",
        }

        try:
            data = await self._request("/orders/asks", params)
        except (RateLimitError, APIError) as e:
            logger.error("magiceden.listings.failed", error=str(e))
            return []

        # Response has an "asks" key in v4 API
        orders = data if isinstance(data, list) else data.get("asks", [])
        listings: list[NFTListingEvent] = []

        for order in orders:
            try:
                # Extract token ID from assetId (format: "contract:tokenId")
                asset_id = order.get("assetId", "")
                token_id = asset_id.split(":")[-1] if ":" in asset_id else ""

                # Parse timestamp (ISO format string)
                created_at = order.get("createdAt")
                if isinstance(created_at, int):
                    timestamp = datetime.fromtimestamp(created_at, tz=UTC)
                elif isinstance(created_at, str):
                    timestamp = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                else:
                    timestamp = datetime.now(UTC)

                # Skip if before since timestamp
                if since and timestamp < since:
                    continue

                # Parse price from nested structure: price.amount.native
                price_data = order.get("price", {})
                amount_data = price_data.get("amount", {}) if isinstance(price_data, dict) else {}

                if isinstance(amount_data, dict):
                    # v4 API: price.amount.native is the decimal string
                    native_price = amount_data.get("native", "0")
                    price_native = Decimal(str(native_price))

                    # USD price is in price.amount.fiat.usd
                    fiat_data = amount_data.get("fiat", {})
                    if isinstance(fiat_data, dict) and fiat_data.get("usd"):
                        price_usd = Decimal(str(fiat_data["usd"]))
                    else:
                        price_usd = None
                else:
                    price_native = Decimal(str(amount_data)) if amount_data else Decimal(0)
                    price_usd = None

                # Use consistent internal identifier for marketplace
                marketplace = "magic_eden"

                listing = NFTListingEvent(
                    collection_id=collection_db_id,
                    token_id=token_id,
                    token_name=None,  # v4 API doesn't include token name in asks
                    token_image_url=None,  # v4 API doesn't include image in asks
                    seller_address=order.get("maker", ""),
                    marketplace=marketplace,
                    price_native=price_native,
                    price_usd=price_usd,
                    floor_price_native=None,  # Will fetch separately if needed
                    rarity_rank=None,  # v4 API doesn't include rarity in asks
                    listing_id=str(order.get("id", "")),
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
        collection_slug: str | None = None,
    ) -> list[NFTSaleEvent]:
        """Fetch sales for a collection.

        Args:
            contract_address: NFT contract address
            chain: Blockchain network
            since: Only fetch sales after this timestamp
            collection_db_id: Database ID of the collection
            collection_slug: Collection slug (not used by Magic Eden, uses contract address)

        Returns:
            List of NFTSaleEvent objects
        """
        if collection_db_id is None:
            logger.warning("magiceden.sales.no_collection_id")
            return []

        chain_lower = self._validate_chain(chain)

        params: dict[str, Any] = {
            "chain": chain_lower,
            "collectionId": contract_address.lower(),
            "activityTypes[]": "TRADE",  # TRADE is the activity type for sales
            "limit": 50,
        }
        # Note: fromTime filtering done after fetch since API format is unclear

        try:
            data = await self._request("/activities", params)
        except (RateLimitError, APIError) as e:
            logger.error("magiceden.sales.failed", error=str(e))
            return []

        # Response has activities array
        activities = data.get("activities", []) if isinstance(data, dict) else []
        sales: list[NFTSaleEvent] = []

        for activity in activities:
            try:
                # Only process TRADE activities
                if activity.get("activityType") != "TRADE":
                    continue

                # Parse timestamp (ISO format string)
                timestamp_str = activity.get("timestamp")
                if timestamp_str:
                    timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                else:
                    timestamp = datetime.now(UTC)

                # Skip if before since timestamp
                if since and timestamp < since:
                    continue

                # Parse price from unitPrice.amount.native (v4 API structure)
                unit_price = activity.get("unitPrice", {})
                amount_data = unit_price.get("amount", {}) if isinstance(unit_price, dict) else {}

                if isinstance(amount_data, dict):
                    price_native = Decimal(str(amount_data.get("native", "0")))
                    # USD is in amount.fiat.usd
                    fiat_data = amount_data.get("fiat", {})
                    price_usd = Decimal(str(fiat_data["usd"])) if fiat_data.get("usd") else None
                else:
                    price_native = Decimal("0")
                    price_usd = None

                asset = activity.get("asset", {})
                tx_info = activity.get("transactionInfo", {})

                # Get image from mediaV2.main.uri
                media_v2 = asset.get("mediaV2", {})
                main_media = media_v2.get("main", {}) if isinstance(media_v2, dict) else {}
                image_url = main_media.get("uri") if isinstance(main_media, dict) else None

                # Get rarity from rarity[0].rank
                rarity_list = asset.get("rarity", [])
                rarity_rank = rarity_list[0].get("rank") if rarity_list else None

                # Use consistent internal identifier for marketplace
                marketplace = "magic_eden"

                sale_event = NFTSaleEvent(
                    collection_id=collection_db_id,
                    token_id=str(asset.get("tokenId", "")),
                    token_name=asset.get("name"),
                    token_image_url=image_url,
                    seller_address=activity.get("fromAddress", ""),
                    buyer_address=activity.get("toAddress", ""),
                    marketplace=marketplace,
                    price_native=price_native,
                    price_usd=price_usd,
                    floor_price_native=None,
                    rarity_rank=rarity_rank,
                    sale_id=tx_info.get("transactionId", activity.get("activityId", "")),
                    event_timestamp=timestamp,
                )
                sales.append(sale_event)

            except Exception as e:
                logger.warning("magiceden.sale.parse_failed", error=str(e))
                continue

        logger.info("magiceden.sales.fetched", count=len(sales), contract=contract_address[:10])
        return sales

    async def get_token_metadata(
        self,
        contract_address: str,
        chain: str,
        token_id: str,
    ) -> dict[str, Any]:
        """Fetch metadata for a single token.

        Args:
            contract_address: NFT contract address
            chain: Blockchain network
            token_id: Token ID

        Returns:
            Dict with token_name and token_image_url (may be None)
        """
        chain_lower = self._validate_chain(chain)

        # Use the tokens endpoint to get metadata
        endpoint = f"/tokens/{chain_lower}/{contract_address.lower()}:{token_id}"

        try:
            data = await self._request(endpoint)
        except (RateLimitError, APIError) as e:
            logger.debug("magiceden.token_metadata.failed", token_id=token_id, error=str(e))
            return {"token_name": None, "token_image_url": None}

        if not data:
            return {"token_name": None, "token_image_url": None}

        # Token data structure
        token = data if isinstance(data, dict) else {}

        # Get name
        token_name = token.get("name")

        # Get image from mediaV2.main.uri or fallback to media
        media_v2 = token.get("mediaV2", {})
        main_media = media_v2.get("main", {}) if isinstance(media_v2, dict) else {}
        image_url = main_media.get("uri") if isinstance(main_media, dict) else None

        # Fallback to older media format
        if not image_url:
            media = token.get("media", {})
            if isinstance(media, dict):
                image_url = media.get("image") or media.get("uri")

        return {"token_name": token_name, "token_image_url": image_url}

    async def get_floor_price(
        self,
        contract_address: str,
        chain: str,
    ) -> Decimal | None:
        """Get current floor price for a collection.

        Uses the asks endpoint sorted by price to get the lowest listing.

        Args:
            contract_address: NFT contract address
            chain: Blockchain network

        Returns:
            Floor price in native currency, or None if unavailable
        """
        chain_lower = self._validate_chain(chain)

        params: dict[str, Any] = {
            "chain": chain_lower,
            "collectionId": contract_address.lower(),
            "sortBy": "price",
            "sortDir": "asc",
            "limit": 1,
            "status[]": "active",
        }

        try:
            data = await self._request("/orders/asks", params)
        except (RateLimitError, APIError) as e:
            logger.warning("magiceden.floor.failed", error=str(e))
            return None

        asks = data if isinstance(data, list) else data.get("asks", [])
        if not asks:
            return None

        # v4 API: price is nested as price.amount.native
        price_data = asks[0].get("price", {})
        if isinstance(price_data, dict):
            amount_data = price_data.get("amount", {})
            if isinstance(amount_data, dict):
                price = amount_data.get("native")
            else:
                price = amount_data
        else:
            price = price_data

        if price is not None:
            return Decimal(str(price))
        return None

    async def get_delistings(
        self,
        contract_address: str,
        chain: str,
        since: datetime | None = None,
        collection_db_id: int | None = None,
        collection_slug: str | None = None,
    ) -> list[NFTDelistingEvent]:
        """Fetch cancelled listings.

        Magic Eden v4 API doesn't have a direct delistings endpoint.

        Args:
            contract_address: NFT contract address
            chain: Blockchain network
            since: Only fetch delistings after this timestamp
            collection_db_id: Database ID of the collection
            collection_slug: Collection slug (not used by Magic Eden)

        Returns:
            Empty list - delistings not supported via this API
        """
        return []

    async def close(self) -> None:
        """Close the HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None
