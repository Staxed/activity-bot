"""GitHub API client with retry logic and rate limit handling."""

import asyncio
from typing import Any

import aiohttp

from app.core.logging import get_logger
from app.shared.exceptions import GitHubAPIError

logger = get_logger(__name__)


class GitHubClient:
    """Async GitHub API client with automatic retry logic.

    Provides methods to interact with GitHub API including authentication
    validation and event fetching with exponential backoff retry.

    Attributes:
        BASE_URL: GitHub API base URL
        MAX_RETRIES: Maximum number of retry attempts
        RETRY_DELAYS: Exponential backoff delays in seconds
    """

    BASE_URL = "https://api.github.com"
    MAX_RETRIES = 3
    RETRY_DELAYS = [2, 4, 8]

    def __init__(self, token: str) -> None:
        """Initialize GitHub client with authentication token.

        Args:
            token: GitHub personal access token
        """
        self.token = token
        self.session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "GitHubClient":
        """Context manager entry: create aiohttp session.

        Returns:
            Self for use in async with statement
        """
        self.session = aiohttp.ClientSession(
            headers={
                "Authorization": f"token {self.token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "activity-bot",
            }
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Context manager exit: close aiohttp session.

        Args:
            exc_type: Exception type if raised
            exc_val: Exception value if raised
            exc_tb: Exception traceback if raised
        """
        if self.session:
            await self.session.close()

    async def get_authenticated_user(self) -> str:
        """Get authenticated user's username.

        Returns:
            GitHub username of the authenticated user

        Raises:
            GitHubAPIError: If authentication fails or network error occurs
        """
        for attempt in range(self.MAX_RETRIES):
            try:
                if not self.session:
                    raise GitHubAPIError("Session not initialized")

                async with self.session.get(f"{self.BASE_URL}/user") as response:
                    if response.status == 200:
                        data = await response.json()
                        username: str = data["login"]
                        return username
                    elif response.status in (401, 403):
                        raise GitHubAPIError(f"Invalid token: {response.status}")
                    else:
                        raise GitHubAPIError(f"API error: {response.status}")
            except aiohttp.ClientError as e:
                if attempt < self.MAX_RETRIES - 1:
                    logger.warning(
                        "github.auth.retry",
                        attempt=attempt + 1,
                        error=str(e),
                    )
                    await asyncio.sleep(self.RETRY_DELAYS[attempt])
                else:
                    raise GitHubAPIError(f"Network error: {e}") from e

        raise GitHubAPIError("Failed to authenticate after retries")

    async def fetch_user_events(self, username: str, page: int = 1) -> list[dict[str, Any]]:
        """Fetch user events from GitHub API.

        Args:
            username: GitHub username to fetch events for
            page: Page number for pagination (default: 1)

        Returns:
            List of event dictionaries from GitHub API

        Raises:
            GitHubAPIError: If API request fails or network error occurs
        """
        url = f"{self.BASE_URL}/users/{username}/events"
        params = {"page": page, "per_page": 30}

        for attempt in range(self.MAX_RETRIES):
            try:
                if not self.session:
                    raise GitHubAPIError("Session not initialized")

                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        data: list[dict[str, Any]] = await response.json()
                        return data
                    elif response.status == 404:
                        logger.info("github.user.not_found", username=username)
                        return []
                    elif response.status in (403, 429):
                        remaining = response.headers.get("x-ratelimit-remaining")
                        reset = response.headers.get("x-ratelimit-reset")
                        logger.warning(
                            "github.ratelimit",
                            remaining=remaining,
                            reset=reset,
                            status=response.status,
                        )
                        raise GitHubAPIError(f"Rate limited: {response.status}")
                    else:
                        raise GitHubAPIError(f"API error: {response.status}")
            except aiohttp.ClientError as e:
                if attempt < self.MAX_RETRIES - 1:
                    logger.warning(
                        "github.events.retry",
                        attempt=attempt + 1,
                        error=str(e),
                        page=page,
                    )
                    await asyncio.sleep(self.RETRY_DELAYS[attempt])
                else:
                    raise GitHubAPIError(f"Network error: {e}") from e

        return []

    async def compare_commits(
        self, owner: str, repo: str, base: str, head: str
    ) -> list[dict[str, Any]]:
        """Fetch commits between two SHAs using GitHub comparison API.

        Args:
            owner: Repository owner
            repo: Repository name
            base: Base commit SHA (older)
            head: Head commit SHA (newer)

        Returns:
            List of commit dictionaries from comparison API

        Raises:
            GitHubAPIError: If API request fails or network error occurs

        Example:
            >>> commits = await client.compare_commits(
            ...     "owner", "repo",
            ...     "abc123", "def456"
            ... )
        """
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/compare/{base}...{head}"

        for attempt in range(self.MAX_RETRIES):
            try:
                if not self.session:
                    raise GitHubAPIError("Session not initialized")

                async with self.session.get(url) as response:
                    if response.status == 200:
                        data: dict[str, Any] = await response.json()
                        commits: list[dict[str, Any]] = data.get("commits", [])
                        return commits
                    elif response.status == 404:
                        logger.warning(
                            "github.compare.not_found",
                            owner=owner,
                            repo=repo,
                            base=base[:7],
                            head=head[:7],
                        )
                        return []
                    elif response.status in (403, 429):
                        remaining = response.headers.get("x-ratelimit-remaining")
                        reset = response.headers.get("x-ratelimit-reset")
                        logger.warning(
                            "github.ratelimit",
                            remaining=remaining,
                            reset=reset,
                            status=response.status,
                        )
                        raise GitHubAPIError(f"Rate limited: {response.status}")
                    else:
                        raise GitHubAPIError(f"API error: {response.status}")
            except aiohttp.ClientError as e:
                if attempt < self.MAX_RETRIES - 1:
                    logger.warning(
                        "github.compare.retry",
                        attempt=attempt + 1,
                        error=str(e),
                    )
                    await asyncio.sleep(self.RETRY_DELAYS[attempt])
                else:
                    raise GitHubAPIError(f"Network error: {e}") from e

        return []
