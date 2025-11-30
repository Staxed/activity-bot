"""Abstract base class for marketplace clients."""

from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.nft.models import NFTDelistingEvent, NFTListingEvent, NFTSaleEvent


class MarketplaceClient(ABC):
    """Abstract base class for NFT marketplace API clients.

    All marketplace implementations must inherit from this class
    and implement the required methods.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Get marketplace name identifier.

        Returns:
            Marketplace name (e.g., "magic_eden", "opensea", "rarible")
        """
        pass

    @abstractmethod
    async def get_listings(
        self,
        contract_address: str,
        chain: str,
        since: datetime | None = None,
        collection_db_id: int | None = None,
    ) -> list["NFTListingEvent"]:
        """Fetch new listings for a collection.

        Args:
            contract_address: NFT contract address
            chain: Blockchain network
            since: Only fetch listings after this timestamp
            collection_db_id: Database ID of the collection (for event creation)

        Returns:
            List of NFTListingEvent objects
        """
        pass

    @abstractmethod
    async def get_sales(
        self,
        contract_address: str,
        chain: str,
        since: datetime | None = None,
        collection_db_id: int | None = None,
    ) -> list["NFTSaleEvent"]:
        """Fetch new sales for a collection.

        Args:
            contract_address: NFT contract address
            chain: Blockchain network
            since: Only fetch sales after this timestamp
            collection_db_id: Database ID of the collection (for event creation)

        Returns:
            List of NFTSaleEvent objects
        """
        pass

    @abstractmethod
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
            Floor price in native currency (ETH), or None if unavailable
        """
        pass

    async def get_delistings(
        self,
        contract_address: str,
        chain: str,
        since: datetime | None = None,
        collection_db_id: int | None = None,
    ) -> list["NFTDelistingEvent"]:
        """Fetch cancelled listings for a collection.

        This is optional - not all marketplaces expose this data.
        Default implementation returns empty list.

        Args:
            contract_address: NFT contract address
            chain: Blockchain network
            since: Only fetch delistings after this timestamp
            collection_db_id: Database ID of the collection (for event creation)

        Returns:
            List of NFTDelistingEvent objects
        """
        return []

    @abstractmethod
    async def close(self) -> None:
        """Close the client and cleanup resources."""
        pass


class MarketplaceError(Exception):
    """Base exception for marketplace API errors."""

    pass


class RateLimitError(MarketplaceError):
    """Raised when API rate limit is hit."""

    def __init__(self, retry_after: int | None = None) -> None:
        """Initialize rate limit error.

        Args:
            retry_after: Seconds to wait before retrying
        """
        self.retry_after = retry_after
        super().__init__(
            f"Rate limited. Retry after {retry_after}s" if retry_after else "Rate limited"
        )


class APIError(MarketplaceError):
    """Raised when API returns an error response."""

    def __init__(self, status: int, message: str) -> None:
        """Initialize API error.

        Args:
            status: HTTP status code
            message: Error message
        """
        self.status = status
        super().__init__(f"API error {status}: {message}")
