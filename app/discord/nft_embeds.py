"""Discord embed builders for NFT events."""

from decimal import Decimal

import discord

from app.discord.nft_event_colors import (
    BURN_COLOR,
    DELISTING_COLOR,
    LISTING_COLOR,
    MINT_COLOR,
    SALE_COLOR,
    TRANSFER_COLOR,
)
from app.nft.models import (
    NFTBurnEvent,
    NFTDelistingEvent,
    NFTListingEvent,
    NFTMintEvent,
    NFTSaleEvent,
    NFTTransferEvent,
)


def _format_eth_price(price: Decimal | None, price_usd: Decimal | None = None) -> str:
    """Format ETH price with optional USD value.

    Args:
        price: Price in ETH
        price_usd: Optional USD value

    Returns:
        Formatted price string
    """
    if price is None:
        return "N/A"

    eth_str = f"{price:.4f}".rstrip("0").rstrip(".") + " ETH"

    if price_usd is not None:
        usd_str = f"${price_usd:,.2f}"
        return f"{eth_str} ({usd_str})"

    return eth_str


def _format_floor_comparison(price: Decimal, floor: Decimal | None) -> str | None:
    """Format price as multiple of floor.

    Args:
        price: Event price
        floor: Floor price

    Returns:
        Formatted comparison string, or None if no floor
    """
    if floor is None or floor <= 0:
        return None

    multiple = float(price / floor)
    if multiple >= 1.0:
        return f"{multiple:.1f}x floor"
    else:
        pct = (1 - multiple) * 100
        return f"{pct:.0f}% below floor"


def create_mint_embed(event: NFTMintEvent, collection_name: str) -> discord.Embed:
    """Create Discord embed for mint event.

    Args:
        event: Mint event data
        collection_name: Human-readable collection name

    Returns:
        Discord embed ready to send
    """
    embed = discord.Embed(
        title=f"🎨 New Mint | {collection_name} #{event.token_id}",
        color=MINT_COLOR,
        timestamp=event.event_timestamp,
    )

    embed.add_field(
        name="Minted by",
        value=f"`{event.short_to_address}`",
        inline=True,
    )

    if event.price_native is not None:
        embed.add_field(
            name="Price",
            value=_format_eth_price(event.price_native, event.price_usd),
            inline=True,
        )

    if event.transaction_hash:
        # Link to block explorer based on chain (default to basescan)
        explorer_url = f"https://basescan.org/tx/{event.transaction_hash}"
        embed.add_field(
            name="Transaction",
            value=f"[View on Explorer]({explorer_url})",
            inline=True,
        )

    embed.set_footer(text=f"Token ID: {event.token_id}")

    return embed


def create_transfer_embed(event: NFTTransferEvent, collection_name: str) -> discord.Embed:
    """Create Discord embed for transfer event.

    Args:
        event: Transfer event data
        collection_name: Human-readable collection name

    Returns:
        Discord embed ready to send
    """
    embed = discord.Embed(
        title=f"🔄 Transfer | {collection_name} #{event.token_id}",
        color=TRANSFER_COLOR,
        timestamp=event.event_timestamp,
    )

    embed.add_field(
        name="From",
        value=f"`{event.short_from_address}`",
        inline=True,
    )

    embed.add_field(
        name="To",
        value=f"`{event.short_to_address}`",
        inline=True,
    )

    if event.transaction_hash:
        explorer_url = f"https://basescan.org/tx/{event.transaction_hash}"
        embed.add_field(
            name="Transaction",
            value=f"[View on Explorer]({explorer_url})",
            inline=True,
        )

    embed.set_footer(text=f"Token ID: {event.token_id}")

    return embed


def create_burn_embed(event: NFTBurnEvent, collection_name: str) -> discord.Embed:
    """Create Discord embed for burn event.

    Args:
        event: Burn event data
        collection_name: Human-readable collection name

    Returns:
        Discord embed ready to send
    """
    embed = discord.Embed(
        title=f"🔥 Burned | {collection_name} #{event.token_id}",
        color=BURN_COLOR,
        timestamp=event.event_timestamp,
    )

    embed.add_field(
        name="Burned by",
        value=f"`{event.short_from_address}`",
        inline=True,
    )

    if event.transaction_hash:
        explorer_url = f"https://basescan.org/tx/{event.transaction_hash}"
        embed.add_field(
            name="Transaction",
            value=f"[View on Explorer]({explorer_url})",
            inline=True,
        )

    embed.set_footer(text=f"Token ID: {event.token_id}")

    return embed


def create_listing_embed(event: NFTListingEvent, collection_name: str) -> discord.Embed:
    """Create Discord embed for listing event.

    Args:
        event: Listing event data
        collection_name: Human-readable collection name

    Returns:
        Discord embed ready to send
    """
    # Use token name if available, otherwise collection + token ID
    title_name = event.token_name or f"{collection_name} #{event.token_id}"

    embed = discord.Embed(
        title=f"📋 Listed | {title_name}",
        color=LISTING_COLOR,
        timestamp=event.event_timestamp,
    )

    embed.add_field(
        name="Seller",
        value=f"`{event.short_seller_address}`",
        inline=True,
    )

    embed.add_field(
        name="Price",
        value=_format_eth_price(event.price_native, event.price_usd),
        inline=True,
    )

    # Floor comparison
    if event.floor_price_native:
        floor_str = _format_eth_price(event.floor_price_native)
        comparison = _format_floor_comparison(event.price_native, event.floor_price_native)
        floor_display = f"{floor_str}"
        if comparison:
            floor_display += f" ({comparison})"
        embed.add_field(
            name="Floor",
            value=floor_display,
            inline=True,
        )

    # Rarity if available
    if event.rarity_rank:
        embed.add_field(
            name="Rarity",
            value=f"#{event.rarity_rank}",
            inline=True,
        )

    # Marketplace
    marketplace_display = event.marketplace.replace("_", " ").title()
    embed.add_field(
        name="Marketplace",
        value=marketplace_display,
        inline=True,
    )

    # Set thumbnail if image available
    if event.token_image_url:
        embed.set_thumbnail(url=event.token_image_url)

    embed.set_footer(text=f"{collection_name} • Token ID: {event.token_id}")

    return embed


def create_sale_embed(event: NFTSaleEvent, collection_name: str) -> discord.Embed:
    """Create Discord embed for sale event.

    Args:
        event: Sale event data
        collection_name: Human-readable collection name

    Returns:
        Discord embed ready to send
    """
    # Use token name if available, otherwise collection + token ID
    title_name = event.token_name or f"{collection_name} #{event.token_id}"

    embed = discord.Embed(
        title=f"💰 Sold | {title_name}",
        color=SALE_COLOR,
        timestamp=event.event_timestamp,
    )

    embed.add_field(
        name="Seller",
        value=f"`{event.short_seller_address}`",
        inline=True,
    )

    embed.add_field(
        name="Buyer",
        value=f"`{event.short_buyer_address}`",
        inline=True,
    )

    embed.add_field(
        name="Price",
        value=_format_eth_price(event.price_native, event.price_usd),
        inline=True,
    )

    # Floor comparison
    if event.floor_price_native:
        floor_str = _format_eth_price(event.floor_price_native)
        comparison = _format_floor_comparison(event.price_native, event.floor_price_native)
        floor_display = f"{floor_str}"
        if comparison:
            floor_display += f" ({comparison})"
        embed.add_field(
            name="Floor",
            value=floor_display,
            inline=True,
        )

    # Rarity if available
    if event.rarity_rank:
        embed.add_field(
            name="Rarity",
            value=f"#{event.rarity_rank}",
            inline=True,
        )

    # Marketplace
    marketplace_display = event.marketplace.replace("_", " ").title()
    embed.add_field(
        name="Marketplace",
        value=marketplace_display,
        inline=True,
    )

    # Set thumbnail if image available
    if event.token_image_url:
        embed.set_thumbnail(url=event.token_image_url)

    embed.set_footer(text=f"{collection_name} • Token ID: {event.token_id}")

    return embed


def create_delisting_embed(event: NFTDelistingEvent, collection_name: str) -> discord.Embed:
    """Create Discord embed for delisting (cancelled listing) event.

    Args:
        event: Delisting event data
        collection_name: Human-readable collection name

    Returns:
        Discord embed ready to send
    """
    # Use token name if available, otherwise collection + token ID
    title_name = event.token_name or f"{collection_name} #{event.token_id}"

    embed = discord.Embed(
        title=f"❌ Delisted | {title_name}",
        color=DELISTING_COLOR,
        timestamp=event.event_timestamp,
    )

    embed.add_field(
        name="Seller",
        value=f"`{event.short_seller_address}`",
        inline=True,
    )

    if event.original_price_native:
        embed.add_field(
            name="Was Listed",
            value=_format_eth_price(event.original_price_native),
            inline=True,
        )

    # Marketplace
    marketplace_display = event.marketplace.replace("_", " ").title()
    embed.add_field(
        name="Marketplace",
        value=marketplace_display,
        inline=True,
    )

    embed.set_footer(text=f"{collection_name} • Token ID: {event.token_id}")

    return embed
