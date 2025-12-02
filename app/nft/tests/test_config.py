"""Tests for NFT configuration loading and validation."""

import json
import tempfile
from pathlib import Path

import pytest

from app.nft.config import (
    NFTCollectionConfig,
    NFTCollectionsConfig,
    load_collections_config,
    reset_collections_config,
)
from app.shared.exceptions import ConfigError


class TestNFTCollectionConfig:
    """Tests for NFTCollectionConfig model."""

    def test_valid_config(self) -> None:
        """Test creating a valid collection config."""
        config = NFTCollectionConfig(
            id="test-collection",
            name="Test Collection",
            chain="base",
            contract_address="0x1234567890123456789012345678901234567890",
            discord_channel_id=123456789,
        )

        assert config.id == "test-collection"
        assert config.name == "Test Collection"
        assert config.chain == "base"
        assert config.contract_address == "0x1234567890123456789012345678901234567890"
        assert config.discord_channel_id == 123456789
        assert config.track_onchain is True
        assert config.track_marketplace is True
        assert config.is_active is True

    def test_contract_address_normalized_to_lowercase(self) -> None:
        """Test that contract address is normalized to lowercase."""
        config = NFTCollectionConfig(
            id="test",
            name="Test",
            chain="base",
            contract_address="0xABCDEF1234567890ABCDEF1234567890ABCDEF12",
            discord_channel_id=123,
        )

        assert config.contract_address == "0xabcdef1234567890abcdef1234567890abcdef12"

    def test_invalid_contract_address_no_prefix(self) -> None:
        """Test that contract address without 0x prefix fails."""
        with pytest.raises(ValueError, match="must start with 0x"):
            NFTCollectionConfig(
                id="test",
                name="Test",
                chain="base",
                contract_address="1234567890123456789012345678901234567890",
                discord_channel_id=123,
            )

    def test_invalid_contract_address_wrong_length(self) -> None:
        """Test that contract address with wrong length fails."""
        with pytest.raises(ValueError, match="must be 42 characters"):
            NFTCollectionConfig(
                id="test",
                name="Test",
                chain="base",
                contract_address="0x1234",
                discord_channel_id=123,
            )

    def test_chain_normalized_to_lowercase(self) -> None:
        """Test that chain is normalized to lowercase."""
        config = NFTCollectionConfig(
            id="test",
            name="Test",
            chain="BASE",
            contract_address="0x1234567890123456789012345678901234567890",
            discord_channel_id=123,
        )

        assert config.chain == "base"

    def test_invalid_chain(self) -> None:
        """Test that unsupported chain fails validation."""
        with pytest.raises(ValueError, match="Chain must be one of"):
            NFTCollectionConfig(
                id="test",
                name="Test",
                chain="solana",
                contract_address="0x1234567890123456789012345678901234567890",
                discord_channel_id=123,
            )

    def test_marketplaces_normalized_to_lowercase(self) -> None:
        """Test that marketplace names are normalized to lowercase."""
        config = NFTCollectionConfig(
            id="test",
            name="Test",
            chain="base",
            contract_address="0x1234567890123456789012345678901234567890",
            discord_channel_id=123,
            marketplaces=["MAGIC_EDEN", "OpenSea"],
        )

        assert config.marketplaces == ["magic_eden", "opensea"]

    def test_invalid_marketplace(self) -> None:
        """Test that unsupported marketplace fails validation."""
        with pytest.raises(ValueError, match="Unsupported marketplaces"):
            NFTCollectionConfig(
                id="test",
                name="Test",
                chain="base",
                contract_address="0x1234567890123456789012345678901234567890",
                discord_channel_id=123,
                marketplaces=["blur"],
            )


class TestNFTCollectionsConfig:
    """Tests for NFTCollectionsConfig container."""

    def test_active_collections_filter(self) -> None:
        """Test filtering for active collections only."""
        config = NFTCollectionsConfig(
            collections=[
                NFTCollectionConfig(
                    id="active",
                    name="Active",
                    chain="base",
                    contract_address="0x1111111111111111111111111111111111111111",
                    discord_channel_id=1,
                    is_active=True,
                ),
                NFTCollectionConfig(
                    id="inactive",
                    name="Inactive",
                    chain="base",
                    contract_address="0x2222222222222222222222222222222222222222",
                    discord_channel_id=2,
                    is_active=False,
                ),
            ]
        )

        active = config.active_collections
        assert len(active) == 1
        assert active[0].id == "active"

    def test_get_collection_by_id(self) -> None:
        """Test finding collection by ID."""
        config = NFTCollectionsConfig(
            collections=[
                NFTCollectionConfig(
                    id="test-1",
                    name="Test 1",
                    chain="base",
                    contract_address="0x1111111111111111111111111111111111111111",
                    discord_channel_id=1,
                ),
            ]
        )

        found = config.get_collection_by_id("test-1")
        assert found is not None
        assert found.name == "Test 1"

        not_found = config.get_collection_by_id("nonexistent")
        assert not_found is None

    def test_get_collection_by_contract(self) -> None:
        """Test finding collection by chain and contract."""
        config = NFTCollectionsConfig(
            collections=[
                NFTCollectionConfig(
                    id="test-1",
                    name="Test 1",
                    chain="base",
                    contract_address="0x1111111111111111111111111111111111111111",
                    discord_channel_id=1,
                ),
            ]
        )

        found = config.get_collection_by_contract(
            "BASE", "0x1111111111111111111111111111111111111111"
        )
        assert found is not None
        assert found.id == "test-1"

        not_found = config.get_collection_by_contract(
            "ethereum", "0x1111111111111111111111111111111111111111"
        )
        assert not_found is None


class TestLoadCollectionsConfig:
    """Tests for loading config from JSON file."""

    def setup_method(self) -> None:
        """Reset config singleton before each test."""
        reset_collections_config()

    def test_load_valid_config(self) -> None:
        """Test loading a valid config file."""
        config_data = {
            "collections": [
                {
                    "id": "test-collection",
                    "name": "Test Collection",
                    "chain": "base",
                    "contract_address": "0x1234567890123456789012345678901234567890",
                    "discord_channel_id": 123456789,
                }
            ]
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            temp_path = f.name

        try:
            config = load_collections_config(temp_path)
            assert len(config.collections) == 1
            assert config.collections[0].id == "test-collection"
        finally:
            Path(temp_path).unlink()

    def test_load_missing_file_returns_empty(self) -> None:
        """Test that missing file returns empty config."""
        config = load_collections_config("/nonexistent/path/config.json")
        assert len(config.collections) == 0

    def test_load_invalid_json_raises_error(self) -> None:
        """Test that invalid JSON raises ConfigError."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("invalid json {")
            temp_path = f.name

        try:
            with pytest.raises(ConfigError, match="Invalid JSON"):
                load_collections_config(temp_path)
        finally:
            Path(temp_path).unlink()
