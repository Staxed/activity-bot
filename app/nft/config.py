"""NFT collection configuration loading and validation."""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.core.logging import get_logger
from app.shared.exceptions import ConfigError

logger = get_logger(__name__)


class NFTCollectionConfig(BaseModel):
    """Configuration for a single NFT collection to track.

    Attributes:
        id: Unique identifier for the collection (e.g., "aeon-forge-genesis")
        name: Human-readable collection name
        chain: Blockchain network (e.g., "base", "ethereum")
        contract_address: NFT contract address (checksummed)
        discord_channel_id: Discord channel ID to post events
        track_onchain: Whether to track on-chain events (mint/transfer/burn)
        track_marketplace: Whether to track marketplace events (listings/sales)
        marketplaces: List of marketplaces to track (magic_eden, opensea, rarible)
        is_active: Whether this collection is actively being tracked
    """

    id: str = Field(..., description="Unique collection identifier")
    name: str = Field(..., description="Human-readable collection name")
    chain: str = Field(..., description="Blockchain network")
    contract_address: str = Field(..., description="NFT contract address")
    discord_channel_id: int = Field(..., description="Discord channel ID for notifications")
    track_onchain: bool = Field(True, description="Track on-chain events")
    track_marketplace: bool = Field(True, description="Track marketplace events")
    marketplaces: list[str] = Field(
        default_factory=lambda: ["magic_eden", "opensea", "rarible"],
        description="Marketplaces to track",
    )
    is_active: bool = Field(True, description="Whether collection is active")

    @field_validator("contract_address")
    @classmethod
    def validate_contract_address(cls, v: str) -> str:
        """Validate contract address format.

        Args:
            v: Contract address string

        Returns:
            Lowercase contract address

        Raises:
            ValueError: If address format is invalid
        """
        if not v.startswith("0x"):
            raise ValueError("Contract address must start with 0x")
        if len(v) != 42:
            raise ValueError("Contract address must be 42 characters")
        # Normalize to lowercase for consistent comparisons
        return v.lower()

    @field_validator("chain")
    @classmethod
    def validate_chain(cls, v: str) -> str:
        """Validate chain is supported.

        Args:
            v: Chain name

        Returns:
            Lowercase chain name

        Raises:
            ValueError: If chain is not supported
        """
        supported_chains = {"base", "ethereum", "polygon", "arbitrum", "optimism"}
        v_lower = v.lower()
        if v_lower not in supported_chains:
            raise ValueError(f"Chain must be one of: {', '.join(sorted(supported_chains))}")
        return v_lower

    @field_validator("marketplaces")
    @classmethod
    def validate_marketplaces(cls, v: list[str]) -> list[str]:
        """Validate marketplace names.

        Args:
            v: List of marketplace names

        Returns:
            Lowercase marketplace names

        Raises:
            ValueError: If any marketplace is not supported
        """
        supported = {"magic_eden", "opensea", "rarible"}
        v_lower = [m.lower() for m in v]
        invalid = set(v_lower) - supported
        if invalid:
            raise ValueError(f"Unsupported marketplaces: {invalid}. Must be in: {supported}")
        return v_lower


class NFTCollectionsConfig(BaseModel):
    """Container for all NFT collection configurations.

    Attributes:
        collections: List of NFT collection configurations
    """

    collections: list[NFTCollectionConfig] = Field(
        default_factory=list,
        description="List of NFT collections to track",
    )

    @property
    def active_collections(self) -> list[NFTCollectionConfig]:
        """Get only active collections.

        Returns:
            List of active NFT collections
        """
        return [c for c in self.collections if c.is_active]

    def get_collection_by_id(self, collection_id: str) -> NFTCollectionConfig | None:
        """Find collection by ID.

        Args:
            collection_id: Collection identifier

        Returns:
            Collection config if found, None otherwise
        """
        for collection in self.collections:
            if collection.id == collection_id:
                return collection
        return None

    def get_collection_by_contract(
        self, chain: str, contract_address: str
    ) -> NFTCollectionConfig | None:
        """Find collection by chain and contract address.

        Args:
            chain: Blockchain network
            contract_address: NFT contract address

        Returns:
            Collection config if found, None otherwise
        """
        chain_lower = chain.lower()
        address_lower = contract_address.lower()
        for collection in self.collections:
            if collection.chain == chain_lower and collection.contract_address == address_lower:
                return collection
        return None


# Singleton instance
_collections_config: NFTCollectionsConfig | None = None


def load_collections_config(config_path: str | Path) -> NFTCollectionsConfig:
    """Load NFT collections configuration from JSON file.

    Args:
        config_path: Path to the collections JSON config file

    Returns:
        Validated NFTCollectionsConfig instance

    Raises:
        ConfigError: If file cannot be read or parsed
    """
    global _collections_config

    path = Path(config_path)

    if not path.exists():
        logger.warning("nft.config.not_found", path=str(path))
        _collections_config = NFTCollectionsConfig(collections=[])
        return _collections_config

    try:
        with path.open() as f:
            data: dict[str, Any] = json.load(f)

        _collections_config = NFTCollectionsConfig.model_validate(data)
        logger.info(
            "nft.config.loaded",
            total_collections=len(_collections_config.collections),
            active_collections=len(_collections_config.active_collections),
            path=str(path),
        )
        return _collections_config

    except json.JSONDecodeError as e:
        logger.error("nft.config.json_error", path=str(path), error=str(e))
        raise ConfigError(f"Invalid JSON in {path}: {e}") from e
    except Exception as e:
        logger.error("nft.config.load_error", path=str(path), error=str(e), exc_info=True)
        raise ConfigError(f"Failed to load NFT config from {path}: {e}") from e


def get_collections_config() -> NFTCollectionsConfig:
    """Get the cached NFT collections configuration.

    Returns:
        NFTCollectionsConfig instance

    Raises:
        ConfigError: If config has not been loaded yet
    """
    if _collections_config is None:
        raise ConfigError("NFT collections config not loaded. Call load_collections_config first.")
    return _collections_config


def reset_collections_config() -> None:
    """Reset the cached configuration (mainly for testing)."""
    global _collections_config
    _collections_config = None
