"""Thirdweb Insight webhook event handler."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from app.core.logging import get_logger
from app.nft.config import get_collections_config
from app.nft.marketplaces.magic_eden import MagicEdenClient
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
    - Transfer: all other transfers (only posted if from a company wallet)

    Attributes:
        db: Database client for storing events
        poster: Discord poster for notifications
        company_wallets: List of company wallet addresses (lowercase)
    """

    def __init__(
        self,
        db: "DatabaseClient",
        poster: "NFTPoster | None" = None,
        company_wallets: list[str] | None = None,
    ) -> None:
        """Initialize event handler.

        Args:
            db: Database client
            poster: Optional Discord poster for notifications
            company_wallets: List of company wallet addresses - only transfers
                           FROM these wallets will be posted to Discord
        """
        self.db = db
        self.poster = poster
        self.company_wallets = [w.lower() for w in (company_wallets or [])]
        self._magic_eden_client: MagicEdenClient | None = None

    async def _get_magic_eden_client(self) -> MagicEdenClient | None:
        """Get or create Magic Eden client for fetching token metadata.

        Returns:
            MagicEdenClient instance or None if initialization fails
        """
        if self._magic_eden_client is None:
            try:
                self._magic_eden_client = MagicEdenClient()
            except Exception as e:
                logger.error("handler.magic_eden_client.init_failed", error=str(e))
                return None
        return self._magic_eden_client

    async def _fetch_token_image(
        self,
        contract_address: str,
        chain: str,
        token_id: str,
    ) -> str | None:
        """Fetch token image URL from Magic Eden.

        Args:
            contract_address: NFT contract address
            chain: Blockchain network
            token_id: Token ID

        Returns:
            Image URL or None if not found
        """
        try:
            client = await self._get_magic_eden_client()
            if client is None:
                return None
            metadata = await client.get_token_metadata(
                contract_address=contract_address,
                chain=chain,
                token_id=token_id,
            )
            return metadata.get("token_image_url")
        except Exception as e:
            logger.debug(
                "handler.fetch_image.failed",
                token_id=token_id,
                error=str(e),
            )
            return None

    async def handle_event(self, payload: dict[str, Any]) -> None:
        """Handle incoming Thirdweb webhook event.

        Args:
            payload: Webhook payload containing event data
        """
        logger.info(
            "handler.event.received",
            payload_keys=list(payload.keys()),
        )

        # Thirdweb sends events in a "data" array
        events = payload.get("data", [])
        if not isinstance(events, list):
            events = [events]

        logger.info("handler.events_count", count=len(events))

        for idx, event_wrapper in enumerate(events):
            logger.info(f"handler.processing_event_{idx}", event_keys=list(event_wrapper.keys()) if isinstance(event_wrapper, dict) else "not_dict")
            await self._process_single_event(event_wrapper)

    async def _process_single_event(self, event_wrapper: dict[str, Any]) -> None:
        """Process a single event from Thirdweb webhook."""
        # The actual event data is nested
        event_data = event_wrapper.get("data", {})
        decoded = event_data.get("decoded", {})

        logger.info(
            "handler.event_structure",
            wrapper_type=event_wrapper.get("type"),
            decoded_name=decoded.get("name"),
            has_indexed_params="indexed_params" in decoded,
        )

        # Check if this is a Transfer event
        if decoded.get("name") != "Transfer":
            logger.info("handler.not_transfer_event", event_name=decoded.get("name"))
            return

        # Extract data from decoded params
        indexed_params = decoded.get("indexed_params", {})
        from_address = indexed_params.get("from", "").lower()
        to_address = indexed_params.get("to", "").lower()
        token_id = str(indexed_params.get("tokenId", ""))

        # Validate token_id is not empty
        if not token_id or token_id == "None":
            logger.warning("handler.invalid_token_id", token_id=token_id)
            return

        # Extract chain and contract from event_data
        chain_id = event_data.get("chain_id") or event_data.get("chainId")
        contract_address = (event_data.get("address") or "").lower()
        transaction_hash = event_data.get("transaction_hash") or event_data.get("transactionHash") or ""
        block_number = event_data.get("block_number") or event_data.get("blockNumber") or 0
        block_timestamp = event_data.get("block_timestamp") or event_data.get("blockTimestamp")

        # Map chain ID to name
        chain_id_map: dict[str | int, str] = {
            "8453": "base",
            "84532": "base-sepolia",
            "1": "ethereum",
            "137": "polygon",
            "42161": "arbitrum",
            "10": "optimism",
            8453: "base",
            84532: "base-sepolia",
            1: "ethereum",
            137: "polygon",
            42161: "arbitrum",
            10: "optimism",
        }
        chain = chain_id_map.get(chain_id, str(chain_id) if chain_id else "base")

        logger.info(
            "handler.extracted_transfer",
            from_address=from_address,
            to_address=to_address,
            token_id=token_id,
            chain_id=chain_id,
            chain=chain,
            contract=contract_address,
            tx_hash=transaction_hash[:20] if transaction_hash else "none",
        )

        # Find matching collection
        config = get_collections_config()
        logger.info(
            "handler.collections.available",
            collections=[
                {"id": c.id, "chain": c.chain, "contract": c.contract_address[:10]}
                for c in config.collections
            ],
        )

        collection = config.get_collection_by_contract(chain, contract_address)

        if not collection:
            logger.warning(
                "handler.no_collection_match",
                chain=chain,
                contract=contract_address,
                available_chains=[c.chain for c in config.collections],
                available_contracts=[c.contract_address.lower() for c in config.collections],
            )
            return

        logger.info("handler.collection.matched", collection_id=collection.id, collection_name=collection.name)

        if not collection.track_onchain:
            logger.info("handler.tracking_disabled", collection_id=collection.id)
            return

        # Get collection database ID
        db_collection_id = await self._get_or_create_collection_id(collection.id)
        if not db_collection_id:
            logger.error("handler.no_db_collection", collection_id=collection.id)
            return

        logger.info("handler.db_collection_id", db_id=db_collection_id)

        # Parse timestamp
        if isinstance(block_timestamp, (int, float)):
            timestamp = datetime.fromtimestamp(block_timestamp, tz=UTC)
        else:
            timestamp = datetime.now(UTC)

        # Parse price if available (for mints) - usually not in Transfer events
        price_native: Decimal | None = None
        price_usd: Decimal | None = None

        # Determine event type based on addresses
        logger.info(
            "handler.determining_event_type",
            from_address=from_address,
            to_address=to_address,
            zero_address=ZERO_ADDRESS,
            is_mint=(from_address == ZERO_ADDRESS),
            is_burn=(to_address == ZERO_ADDRESS),
        )

        # Fetch token image for the embed
        token_image_url = await self._fetch_token_image(
            contract_address=contract_address,
            chain=chain,
            token_id=token_id,
        )

        if from_address == ZERO_ADDRESS:
            # Mint event
            logger.info("handler.processing_mint", token_id=token_id)
            await self._handle_mint(
                collection_id=db_collection_id,
                collection_name=collection.name,
                token_id=token_id,
                to_address=to_address,
                transaction_hash=transaction_hash,
                block_number=block_number,
                timestamp=timestamp,
                chain=chain,
                price_native=price_native,
                price_usd=price_usd,
                token_image_url=token_image_url,
                discord_channel_id=collection.discord_channel_id,
            )
        elif to_address == ZERO_ADDRESS:
            # Burn event
            logger.info("handler.processing_burn", token_id=token_id)
            await self._handle_burn(
                collection_id=db_collection_id,
                collection_name=collection.name,
                token_id=token_id,
                from_address=from_address,
                transaction_hash=transaction_hash,
                block_number=block_number,
                timestamp=timestamp,
                chain=chain,
                token_image_url=token_image_url,
                discord_channel_id=collection.discord_channel_id,
            )
        else:
            # Transfer event - only post if from a company wallet
            logger.info("handler.processing_transfer", token_id=token_id)

            # Check if this transfer is from a company wallet
            is_company_transfer = (
                len(self.company_wallets) == 0  # No wallets configured = post all
                or from_address in self.company_wallets
            )

            if not is_company_transfer:
                logger.info(
                    "handler.transfer.skipped_not_company_wallet",
                    token_id=token_id,
                    from_address=from_address[:10] + "...",
                )
                return

            await self._handle_transfer(
                collection_id=db_collection_id,
                collection_name=collection.name,
                token_id=token_id,
                from_address=from_address,
                to_address=to_address,
                transaction_hash=transaction_hash,
                block_number=block_number,
                chain=chain,
                token_image_url=token_image_url,
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
        chain: str,
        price_native: Decimal | None,
        price_usd: Decimal | None,
        token_image_url: str | None,
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
            chain: Blockchain network
            price_native: Mint price in ETH
            price_usd: Mint price in USD
            token_image_url: Token image URL
            discord_channel_id: Discord channel for notifications
        """
        event = NFTMintEvent.from_thirdweb_webhook(
            collection_id=collection_id,
            token_id=token_id,
            to_address=to_address,
            transaction_hash=transaction_hash,
            block_number=block_number,
            timestamp=timestamp,
            chain=chain,
            price_native=price_native,
            price_usd=price_usd,
            token_image_url=token_image_url,
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
        chain: str,
        token_image_url: str | None,
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
            chain: Blockchain network
            token_image_url: Token image URL
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
            chain=chain,
            token_image_url=token_image_url,
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
        chain: str,
        token_image_url: str | None,
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
            chain: Blockchain network
            token_image_url: Token image URL
            discord_channel_id: Discord channel for notifications
        """
        event = NFTBurnEvent.from_thirdweb_webhook(
            collection_id=collection_id,
            token_id=token_id,
            from_address=from_address,
            transaction_hash=transaction_hash,
            block_number=block_number,
            timestamp=timestamp,
            chain=chain,
            token_image_url=token_image_url,
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
