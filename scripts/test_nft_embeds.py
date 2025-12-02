"""Test script to post sample NFT embeds to Discord.

Run with: uv run python scripts/test_nft_embeds.py

This will post one of each embed type (mint, transfer, burn, listing, sale)
to the configured Discord channel for visual testing.
"""

import asyncio
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

# Add parent directory to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

import discord

from app.core.config import get_settings
from app.discord.nft_embeds import (
    create_burn_embed,
    create_listing_embed,
    create_mint_embed,
    create_sale_embed,
    create_transfer_embed,
)
from app.nft.models import (
    NFTBurnEvent,
    NFTListingEvent,
    NFTMintEvent,
    NFTSaleEvent,
    NFTTransferEvent,
)


# Sample image URL for testing - use a direct IPFS gateway URL
SAMPLE_IMAGE_URL = "https://ipfs.io/ipfs/QmYDvPAXtiJg7s8JdRBSLWdgSphQdac8j1YuQNNxcGE1hg/1.png"

# Sample addresses
SAMPLE_SELLER = "0x1234567890abcdef1234567890abcdef12345678"
SAMPLE_BUYER = "0xabcdef1234567890abcdef1234567890abcdef12"
SAMPLE_MINTER = "0x9876543210fedcba9876543210fedcba98765432"
SAMPLE_TX_HASH = "0xabc123def456789abc123def456789abc123def456789abc123def456789abc1"

# Collection name for display
COLLECTION_NAME = "DragonZ Series 1"

# Test chain and contract for Magic Eden links
TEST_CHAIN = "base"
TEST_CONTRACT = "0x1234567890abcdef1234567890abcdef12345678"


def create_sample_mint_event() -> NFTMintEvent:
    """Create a sample mint event for testing."""
    return NFTMintEvent(
        collection_id=1,
        token_id="1337",
        to_address=SAMPLE_MINTER,
        chain="base",
        token_image_url=SAMPLE_IMAGE_URL,
        price_native=Decimal("0.05"),
        price_usd=Decimal("125.50"),
        transaction_hash=SAMPLE_TX_HASH,
        block_number=12345678,
        event_timestamp=datetime.now(UTC),
    )


def create_sample_transfer_event() -> NFTTransferEvent:
    """Create a sample transfer event for testing."""
    return NFTTransferEvent(
        collection_id=1,
        token_id="42",
        from_address=SAMPLE_SELLER,
        to_address=SAMPLE_BUYER,
        chain="base",
        token_image_url=SAMPLE_IMAGE_URL,
        transaction_hash=SAMPLE_TX_HASH,
        block_number=12345679,
        event_timestamp=datetime.now(UTC),
    )


def create_sample_burn_event() -> NFTBurnEvent:
    """Create a sample burn event for testing."""
    return NFTBurnEvent(
        collection_id=1,
        token_id="999",
        from_address=SAMPLE_SELLER,
        chain="base",
        token_image_url=SAMPLE_IMAGE_URL,
        transaction_hash=SAMPLE_TX_HASH,
        block_number=12345680,
        event_timestamp=datetime.now(UTC),
    )


def create_sample_listing_event(with_rarity: bool = False) -> NFTListingEvent:
    """Create a sample listing event for testing."""
    return NFTListingEvent(
        collection_id=1,
        token_id="256",
        token_name=None,
        token_image_url=SAMPLE_IMAGE_URL,
        seller_address=SAMPLE_SELLER,
        marketplace="magic_eden",
        price_native=Decimal("0.15"),
        price_usd=Decimal("375.00"),
        floor_price_native=Decimal("0.10"),
        rarity_rank=42 if with_rarity else None,
        listing_id="listing-123456",
        event_timestamp=datetime.now(UTC),
        is_active=True,
    )


def create_sample_sale_event(with_rarity: bool = False) -> NFTSaleEvent:
    """Create a sample sale event for testing."""
    return NFTSaleEvent(
        collection_id=1,
        token_id="512",
        token_name=None,
        token_image_url=SAMPLE_IMAGE_URL,
        seller_address=SAMPLE_SELLER,
        buyer_address=SAMPLE_BUYER,
        marketplace="magic_eden",
        price_native=Decimal("0.25"),
        price_usd=Decimal("625.00"),
        floor_price_native=Decimal("0.10"),
        rarity_rank=15 if with_rarity else None,
        sale_id=SAMPLE_TX_HASH,
        event_timestamp=datetime.now(UTC),
    )


async def main() -> None:
    """Post sample embeds to Discord for testing."""
    settings = get_settings()

    # Use the NFT channel from the collections config
    channel_id = 1215729486994210897  # DragonZ channel

    print(f"Posting test embeds to channel {channel_id}...")

    # Create Discord client
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready() -> None:
        print(f"Logged in as {client.user}")

        try:
            channel = client.get_channel(channel_id)
            if not channel:
                channel = await client.fetch_channel(channel_id)

            if not isinstance(channel, discord.TextChannel):
                print(f"Error: Channel {channel_id} is not a text channel")
                await client.close()
                return

            print(f"Found channel: #{channel.name}")

            # Post header message
            await channel.send("**--- NFT Embed Test Suite ---**")

            # 1. Mint embed
            print("Posting mint embed...")
            mint_event = create_sample_mint_event()
            mint_embed = create_mint_embed(mint_event, COLLECTION_NAME)
            await channel.send(content="**1. Mint Event**", embed=mint_embed)

            # 2. Transfer embed
            print("Posting transfer embed...")
            transfer_event = create_sample_transfer_event()
            transfer_embed = create_transfer_embed(transfer_event, COLLECTION_NAME)
            await channel.send(content="**2. Transfer Event**", embed=transfer_embed)

            # 3. Burn embed
            print("Posting burn embed...")
            burn_event = create_sample_burn_event()
            burn_embed = create_burn_embed(burn_event, COLLECTION_NAME)
            await channel.send(content="**3. Burn Event**", embed=burn_embed)

            # 4. Listing embed without rarity
            print("Posting listing embed (no rarity)...")
            listing_event = create_sample_listing_event(with_rarity=False)
            listing_embed = create_listing_embed(
                listing_event, COLLECTION_NAME, chain=TEST_CHAIN, contract_address=TEST_CONTRACT
            )
            await channel.send(content="**4. Listing Event** (without rarity)", embed=listing_embed)

            # 5. Listing embed with rarity
            print("Posting listing embed (with rarity)...")
            listing_event_rarity = create_sample_listing_event(with_rarity=True)
            listing_embed_rarity = create_listing_embed(
                listing_event_rarity, COLLECTION_NAME, chain=TEST_CHAIN, contract_address=TEST_CONTRACT
            )
            await channel.send(content="**5. Listing Event** (with rarity)", embed=listing_embed_rarity)

            # 6. Sale embed without rarity
            print("Posting sale embed (no rarity)...")
            sale_event = create_sample_sale_event(with_rarity=False)
            sale_embed = create_sale_embed(sale_event, COLLECTION_NAME, chain=TEST_CHAIN)
            await channel.send(content="**6. Sale Event** (without rarity)", embed=sale_embed)

            # 7. Sale embed with rarity
            print("Posting sale embed (with rarity)...")
            sale_event_rarity = create_sample_sale_event(with_rarity=True)
            sale_embed_rarity = create_sale_embed(sale_event_rarity, COLLECTION_NAME, chain=TEST_CHAIN)
            await channel.send(content="**7. Sale Event** (with rarity)", embed=sale_embed_rarity)

            # Post footer message
            await channel.send("**--- End of Test Suite ---**")

            print("All embeds posted successfully!")

        except Exception as e:
            print(f"Error posting embeds: {e}")
            import traceback
            traceback.print_exc()

        finally:
            await client.close()

    # Run the client
    await client.start(settings.discord_token)


if __name__ == "__main__":
    asyncio.run(main())
