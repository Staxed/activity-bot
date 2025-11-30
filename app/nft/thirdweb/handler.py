"""Thirdweb Insight webhook event handler."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from app.core.logging import get_logger
from app.nft.config import get_collections_config
from app.nft.models import ZERO_ADDRESS, NFTBurnEvent, NFTMintEvent, NFTTransferEvent

if TYPE_CHECKING:
    from app.core.database import DatabaseClient
    from app.discord.nft_poster import NFTPoster

logger = get_logger(__name__)


class ThirdwebEventHandler:
    """Handler for Thirdweb Insight webhook events.

    Processes ERC-721 Transfer events and categorizes them as:
    - Mint: from_address is zero address
    - Burn: to_address is zero address
    - Transfer: all other transfers

    Attributes:
        db: Database client for storing events
        poster: Discord poster for notifications
    """

    def __init__(
        self,
        db: "DatabaseClient",
        poster: "NFTPoster | None" = None,
    ) -> None:
        """Initialize event handler.

        Args:
            db: Database client
            poster: Optional Discord poster for notifications
        """
        self.db = db
        self.poster = poster

    async def handle_event(self, payload: dict[str, Any]) -> None:
        """Handle incoming Thirdweb webhook event.

        Args:
            payload: Webhook payload containing event data
        """
        event_type = payload.get("type", "")

        if event_type != "transfer":
            logger.debug("thirdweb.event.skipped", event_type=event_type)
            return

        # Extract event data
        data = payload.get("data", {})
        contract_address = (
            data.get("contractAddress") or payload.get("contractAddress", "")
        ).lower()
        chain = (data.get("chain") or payload.get("chain", "")).lower()

        # Map chain names to our format
        chain_mapping = {
            "base": "base",
            "base-mainnet": "base",
            "ethereum": "ethereum",
            "eth-mainnet": "ethereum",
            "polygon": "polygon",
            "polygon-mainnet": "polygon",
        }
        chain = chain_mapping.get(chain, chain)

        # Find matching collection
        config = get_collections_config()
        collection = config.get_collection_by_contract(chain, contract_address)

        if not collection:
            logger.debug(
                "thirdweb.event.no_collection",
                chain=chain,
                contract=contract_address[:10] + "...",
            )
            return

        if not collection.track_onchain:
            logger.debug(
                "thirdweb.event.tracking_disabled",
                collection_id=collection.id,
            )
            return

        # Get collection database ID
        db_collection_id = await self._get_or_create_collection_id(collection.id)
        if not db_collection_id:
            logger.error("thirdweb.event.no_db_collection", collection_id=collection.id)
            return

        # Parse transfer event
        from_address = data.get("from", "").lower()
        to_address = data.get("to", "").lower()
        token_id = str(data.get("tokenId", ""))
        transaction_hash = data.get("transactionHash", "")
        block_number = data.get("blockNumber", 0)

        # Parse timestamp
        timestamp_value = data.get("timestamp") or data.get("blockTimestamp")
        if isinstance(timestamp_value, (int, float)):
            timestamp = datetime.fromtimestamp(timestamp_value, tz=UTC)
        elif isinstance(timestamp_value, str):
            timestamp = datetime.fromisoformat(timestamp_value.replace("Z", "+00:00"))
        else:
            timestamp = datetime.now(UTC)

        # Parse price if available (for mints)
        price_native: Decimal | None = None
        price_usd: Decimal | None = None
        if data.get("value"):
            try:
                # Value in wei, convert to ETH
                value_wei = int(data["value"])
                price_native = Decimal(value_wei) / Decimal("1000000000000000000")
            except (ValueError, TypeError):
                pass

        # Determine event type based on addresses
        if from_address == ZERO_ADDRESS:
            # Mint event
            await self._handle_mint(
                collection_id=db_collection_id,
                collection_name=collection.name,
                token_id=token_id,
                to_address=to_address,
                transaction_hash=transaction_hash,
                block_number=block_number,
                timestamp=timestamp,
                price_native=price_native,
                price_usd=price_usd,
                discord_channel_id=collection.discord_channel_id,
            )
        elif to_address == ZERO_ADDRESS:
            # Burn event
            await self._handle_burn(
                collection_id=db_collection_id,
                collection_name=collection.name,
                token_id=token_id,
                from_address=from_address,
                transaction_hash=transaction_hash,
                block_number=block_number,
                timestamp=timestamp,
                discord_channel_id=collection.discord_channel_id,
            )
        else:
            # Transfer event
            await self._handle_transfer(
                collection_id=db_collection_id,
                collection_name=collection.name,
                token_id=token_id,
                from_address=from_address,
                to_address=to_address,
                transaction_hash=transaction_hash,
                block_number=block_number,
                timestamp=timestamp,
                discord_channel_id=collection.discord_channel_id,
            )

    async def _get_or_create_collection_id(self, collection_id: str) -> int | None:
        """Get database ID for collection, creating if needed.

        Args:
            collection_id: Collection string identifier

        Returns:
            Database ID or None if not found/created
        """
        try:
            return await self.db.get_nft_collection_db_id(collection_id)
        except Exception as e:
            logger.error(
                "thirdweb.collection.lookup_failed",
                collection_id=collection_id,
                error=str(e),
            )
            return None

    async def _handle_mint(
        self,
        collection_id: int,
        collection_name: str,
        token_id: str,
        to_address: str,
        transaction_hash: str,
        block_number: int,
        timestamp: datetime,
        price_native: Decimal | None,
        price_usd: Decimal | None,
        discord_channel_id: int,
    ) -> None:
        """Handle mint event.

        Args:
            collection_id: Database collection ID
            collection_name: Collection name for display
            token_id: NFT token ID
            to_address: Minter address
            transaction_hash: Transaction hash
            block_number: Block number
            timestamp: Event timestamp
            price_native: Mint price in ETH
            price_usd: Mint price in USD
            discord_channel_id: Discord channel for notifications
        """
        event = NFTMintEvent.from_thirdweb_webhook(
            collection_id=collection_id,
            token_id=token_id,
            to_address=to_address,
            transaction_hash=transaction_hash,
            block_number=block_number,
            timestamp=timestamp,
            price_native=price_native,
            price_usd=price_usd,
        )

        # Insert to database
        try:
            inserted = await self.db.insert_nft_mint(event)
            if not inserted:
                logger.debug("thirdweb.mint.duplicate", token_id=token_id)
                return
        except Exception as e:
            logger.error("thirdweb.mint.insert_failed", error=str(e), exc_info=True)
            return

        logger.info(
            "thirdweb.mint.processed",
            collection=collection_name,
            token_id=token_id,
            minter=to_address[:10] + "...",
        )

        # Post to Discord
        if self.poster:
            try:
                await self.poster.post_mint(event, collection_name, discord_channel_id)
                await self.db.mark_nft_mint_posted(collection_id, token_id, transaction_hash)
            except Exception as e:
                logger.error("thirdweb.mint.post_failed", error=str(e), exc_info=True)

    async def _handle_transfer(
        self,
        collection_id: int,
        collection_name: str,
        token_id: str,
        from_address: str,
        to_address: str,
        transaction_hash: str,
        block_number: int,
        timestamp: datetime,
        discord_channel_id: int,
    ) -> None:
        """Handle transfer event.

        Args:
            collection_id: Database collection ID
            collection_name: Collection name for display
            token_id: NFT token ID
            from_address: Sender address
            to_address: Recipient address
            transaction_hash: Transaction hash
            block_number: Block number
            timestamp: Event timestamp
            discord_channel_id: Discord channel for notifications
        """
        event = NFTTransferEvent.from_thirdweb_webhook(
            collection_id=collection_id,
            token_id=token_id,
            from_address=from_address,
            to_address=to_address,
            transaction_hash=transaction_hash,
            block_number=block_number,
            timestamp=timestamp,
        )

        # Insert to database
        try:
            inserted = await self.db.insert_nft_transfer(event)
            if not inserted:
                logger.debug("thirdweb.transfer.duplicate", token_id=token_id)
                return
        except Exception as e:
            logger.error("thirdweb.transfer.insert_failed", error=str(e), exc_info=True)
            return

        logger.info(
            "thirdweb.transfer.processed",
            collection=collection_name,
            token_id=token_id,
            from_addr=from_address[:10] + "...",
            to_addr=to_address[:10] + "...",
        )

        # Post to Discord
        if self.poster:
            try:
                await self.poster.post_transfer(event, collection_name, discord_channel_id)
                await self.db.mark_nft_transfer_posted(collection_id, token_id, transaction_hash)
            except Exception as e:
                logger.error("thirdweb.transfer.post_failed", error=str(e), exc_info=True)

    async def _handle_burn(
        self,
        collection_id: int,
        collection_name: str,
        token_id: str,
        from_address: str,
        transaction_hash: str,
        block_number: int,
        timestamp: datetime,
        discord_channel_id: int,
    ) -> None:
        """Handle burn event.

        Args:
            collection_id: Database collection ID
            collection_name: Collection name for display
            token_id: NFT token ID
            from_address: Burner address
            transaction_hash: Transaction hash
            block_number: Block number
            timestamp: Event timestamp
            discord_channel_id: Discord channel for notifications
        """
        event = NFTBurnEvent.from_thirdweb_webhook(
            collection_id=collection_id,
            token_id=token_id,
            from_address=from_address,
            transaction_hash=transaction_hash,
            block_number=block_number,
            timestamp=timestamp,
        )

        # Insert to database
        try:
            inserted = await self.db.insert_nft_burn(event)
            if not inserted:
                logger.debug("thirdweb.burn.duplicate", token_id=token_id)
                return
        except Exception as e:
            logger.error("thirdweb.burn.insert_failed", error=str(e), exc_info=True)
            return

        logger.info(
            "thirdweb.burn.processed",
            collection=collection_name,
            token_id=token_id,
            burner=from_address[:10] + "...",
        )

        # Post to Discord
        if self.poster:
            try:
                await self.poster.post_burn(event, collection_name, discord_channel_id)
                await self.db.mark_nft_burn_posted(collection_id, token_id, transaction_hash)
            except Exception as e:
                logger.error("thirdweb.burn.post_failed", error=str(e), exc_info=True)
