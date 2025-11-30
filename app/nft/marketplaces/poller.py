"""Marketplace polling service for NFT listings and sales."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.core.logging import get_logger
from app.nft.config import NFTCollectionConfig, get_collections_config
from app.nft.marketplaces.base import MarketplaceClient, MarketplaceError
from app.nft.marketplaces.magic_eden import MagicEdenClient
from app.nft.marketplaces.opensea import OpenSeaClient
from app.nft.marketplaces.rarible import RaribleClient

if TYPE_CHECKING:
    from app.core.database import DatabaseClient
    from app.discord.nft_poster import NFTPoster

logger = get_logger(__name__)


class MarketplacePollingService:
    """Service for polling NFT marketplace APIs.

    Polls Magic Eden, OpenSea, and Rarible APIs for new listings and sales
    on configured collections. Uses database state to track last poll time
    for each collection/marketplace pair.

    Attributes:
        poll_interval_minutes: How often to poll (default: 2 minutes)
    """

    def __init__(
        self,
        db: "DatabaseClient",
        poster: "NFTPoster | None" = None,
        poll_interval_minutes: int = 2,
        opensea_api_key: str | None = None,
        rarible_api_key: str | None = None,
    ) -> None:
        """Initialize polling service.

        Args:
            db: Database client
            poster: Optional Discord poster for notifications
            poll_interval_minutes: How often to poll marketplaces
            opensea_api_key: OpenSea API key (required for OpenSea)
            rarible_api_key: Optional Rarible API key
        """
        self.db = db
        self.poster = poster
        self.poll_interval_minutes = poll_interval_minutes
        self.opensea_api_key = opensea_api_key
        self.rarible_api_key = rarible_api_key

        self._running = False
        self._poll_task: asyncio.Task[None] | None = None
        self._clients: dict[str, MarketplaceClient] = {}

    async def start(self) -> None:
        """Start the polling service."""
        if self._running:
            return

        # Initialize marketplace clients
        await self._init_clients()

        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info(
            "marketplace.poller.started",
            interval_minutes=self.poll_interval_minutes,
            marketplaces=list(self._clients.keys()),
        )

    async def stop(self) -> None:
        """Stop the polling service."""
        self._running = False

        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass

        # Close all clients
        for client in self._clients.values():
            await client.close()
        self._clients.clear()

        logger.info("marketplace.poller.stopped")

    async def _init_clients(self) -> None:
        """Initialize marketplace clients."""
        # Magic Eden doesn't require API key
        self._clients["magic_eden"] = MagicEdenClient()

        # OpenSea requires API key
        if self.opensea_api_key:
            self._clients["opensea"] = OpenSeaClient(self.opensea_api_key)
        else:
            logger.warning("marketplace.opensea.no_api_key")

        # Rarible works without key but has rate limits
        self._clients["rarible"] = RaribleClient(self.rarible_api_key)

    async def _poll_loop(self) -> None:
        """Main polling loop."""
        while self._running:
            try:
                await self._poll_all_collections()
            except Exception as e:
                logger.error("marketplace.poll.error", error=str(e), exc_info=True)

            # Wait for next poll interval
            await asyncio.sleep(self.poll_interval_minutes * 60)

    async def _poll_all_collections(self) -> None:
        """Poll all active collections."""
        config = get_collections_config()
        active_collections = [c for c in config.active_collections if c.track_marketplace]

        if not active_collections:
            logger.debug("marketplace.poll.no_collections")
            return

        logger.info("marketplace.poll.started", collections=len(active_collections))

        for collection in active_collections:
            try:
                await self._poll_collection(collection)
            except Exception as e:
                logger.error(
                    "marketplace.poll.collection_error",
                    collection=collection.id,
                    error=str(e),
                    exc_info=True,
                )

        logger.info("marketplace.poll.completed")

    async def _poll_collection(self, collection: NFTCollectionConfig) -> None:
        """Poll a single collection across all configured marketplaces.

        Args:
            collection: Collection configuration
        """
        # Get database ID for collection
        db_collection_id = await self.db.get_nft_collection_db_id(collection.id)
        if not db_collection_id:
            logger.warning("marketplace.poll.no_db_id", collection=collection.id)
            return

        for marketplace_name in collection.marketplaces:
            client = self._clients.get(marketplace_name)
            if not client:
                continue

            try:
                await self._poll_marketplace(
                    collection=collection,
                    db_collection_id=db_collection_id,
                    client=client,
                )
            except MarketplaceError as e:
                logger.warning(
                    "marketplace.poll.marketplace_error",
                    collection=collection.id,
                    marketplace=marketplace_name,
                    error=str(e),
                )

    async def _poll_marketplace(
        self,
        collection: NFTCollectionConfig,
        db_collection_id: int,
        client: MarketplaceClient,
    ) -> None:
        """Poll a single marketplace for a collection.

        Args:
            collection: Collection configuration
            db_collection_id: Database ID of the collection
            client: Marketplace client
        """
        marketplace_name = client.name

        # Get last poll timestamp
        last_poll = await self.db.get_nft_marketplace_state(db_collection_id, marketplace_name)

        # Default to 12 hours ago if no previous poll
        if last_poll is None:
            last_poll = datetime.now(UTC) - timedelta(hours=12)

        # Fetch new listings
        listings = await client.get_listings(
            contract_address=collection.contract_address,
            chain=collection.chain,
            since=last_poll,
            collection_db_id=db_collection_id,
        )

        # Fetch new sales
        sales = await client.get_sales(
            contract_address=collection.contract_address,
            chain=collection.chain,
            since=last_poll,
            collection_db_id=db_collection_id,
        )

        # Fetch delistings if supported
        delistings = await client.get_delistings(
            contract_address=collection.contract_address,
            chain=collection.chain,
            since=last_poll,
            collection_db_id=db_collection_id,
        )

        # Insert listings to database
        for listing in listings:
            try:
                inserted = await self.db.insert_nft_listing(listing)
                if inserted and self.poster:
                    await self.poster.post_listing(
                        listing, collection.name, collection.discord_channel_id
                    )
                    await self.db.mark_nft_listing_posted(
                        db_collection_id, marketplace_name, listing.listing_id
                    )
            except Exception as e:
                logger.warning("marketplace.listing.save_failed", error=str(e))

        # Insert sales to database
        for sale in sales:
            try:
                inserted = await self.db.insert_nft_sale(sale)
                if inserted and self.poster:
                    await self.poster.post_sale(
                        sale, collection.name, collection.discord_channel_id
                    )
                    await self.db.mark_nft_sale_posted(
                        db_collection_id, marketplace_name, sale.sale_id
                    )
            except Exception as e:
                logger.warning("marketplace.sale.save_failed", error=str(e))

        # Insert delistings to database
        for delisting in delistings:
            try:
                inserted = await self.db.insert_nft_delisting(delisting)
                if inserted and self.poster:
                    await self.poster.post_delisting(
                        delisting, collection.name, collection.discord_channel_id
                    )
                    await self.db.mark_nft_delisting_posted(
                        db_collection_id, marketplace_name, delisting.delisting_id
                    )
            except Exception as e:
                logger.warning("marketplace.delisting.save_failed", error=str(e))

        # Update poll state
        await self.db.set_nft_marketplace_state(db_collection_id, marketplace_name)

        logger.info(
            "marketplace.poll.collection_done",
            collection=collection.id,
            marketplace=marketplace_name,
            listings=len(listings),
            sales=len(sales),
            delistings=len(delistings),
        )

    async def poll_now(self) -> None:
        """Trigger an immediate poll of all collections.

        Useful for testing or manual refresh.
        """
        await self._poll_all_collections()
