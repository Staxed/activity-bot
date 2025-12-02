"""Webhook server for receiving Thirdweb Insight events."""

import asyncio
import hashlib
import hmac
from typing import TYPE_CHECKING, Any

from aiohttp import web

from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.nft.thirdweb.handler import ThirdwebEventHandler

logger = get_logger(__name__)


class WebhookServer:
    """Async HTTP server for receiving webhook events.

    Provides endpoints for:
    - POST /webhooks/thirdweb: Thirdweb Insight webhook events
    - GET /health: Health check endpoint

    Attributes:
        host: Server host address
        port: Server port
        webhook_secret: Secret for validating webhook signatures
    """

    def __init__(
        self,
        host: str,
        port: int,
        webhook_secret: str,
        event_handler: "ThirdwebEventHandler | None" = None,
    ) -> None:
        """Initialize webhook server.

        Args:
            host: Host address to bind to
            port: Port to listen on
            webhook_secret: Thirdweb webhook secret for signature validation
            event_handler: Handler for processing webhook events
        """
        self.host = host
        self.port = port
        self.webhook_secret = webhook_secret
        self.event_handler = event_handler
        self.app: web.Application | None = None
        self.runner: web.AppRunner | None = None
        self.site: web.TCPSite | None = None
        self._running = False

    async def start(self) -> None:
        """Start the webhook server.

        Creates and starts the aiohttp web application.
        """
        self.app = web.Application()
        self.app.router.add_get("/health", self._handle_health)
        self.app.router.add_post("/webhooks/thirdweb", self._handle_thirdweb_webhook)

        self.runner = web.AppRunner(self.app)
        await self.runner.setup()

        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()

        self._running = True
        logger.info("webhook.server.started", host=self.host, port=self.port)

    async def stop(self) -> None:
        """Stop the webhook server gracefully."""
        self._running = False

        if self.site:
            await self.site.stop()

        if self.runner:
            await self.runner.cleanup()

        logger.info("webhook.server.stopped")

    @property
    def is_running(self) -> bool:
        """Check if server is running."""
        return self._running

    async def _handle_health(self, request: web.Request) -> web.Response:
        """Handle health check requests.

        Args:
            request: Incoming HTTP request

        Returns:
            JSON response with health status
        """
        return web.json_response({"status": "healthy", "service": "nft-webhook-server"})

    def _verify_signature(self, payload: bytes, signature: str) -> bool:
        """Verify Thirdweb webhook signature.

        Thirdweb uses HMAC-SHA256 over the raw request body.

        Args:
            payload: Raw request body
            signature: Signature from X-Webhook-Signature header

        Returns:
            True if signature is valid, False otherwise
        """
        if not self.webhook_secret:
            logger.warning("webhook.signature.no_secret_configured")
            return False

        expected = hmac.new(
            self.webhook_secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature)

    async def _handle_thirdweb_webhook(self, request: web.Request) -> web.Response:
        """Handle Thirdweb Insight webhook events.

        Validates signature, parses payload, and dispatches to handler.
        Returns 200 immediately and processes asynchronously.

        Args:
            request: Incoming HTTP request

        Returns:
            JSON response acknowledging receipt
        """
        # Read raw body for signature validation
        try:
            body = await request.read()
        except Exception as e:
            logger.error("webhook.read.failed", error=str(e))
            return web.json_response({"error": "Failed to read body"}, status=400)

        # Validate signature
        signature = request.headers.get("X-Webhook-Signature", "")
        if not signature:
            logger.warning("webhook.signature.missing")
            return web.json_response({"error": "Missing signature"}, status=401)

        if not self._verify_signature(body, signature):
            logger.warning("webhook.signature.invalid")
            return web.json_response({"error": "Invalid signature"}, status=401)

        # Parse JSON payload
        try:
            payload: dict[str, Any] = await request.json()
        except Exception as e:
            logger.error("webhook.parse.failed", error=str(e))
            return web.json_response({"error": "Invalid JSON"}, status=400)

        # Log full payload for debugging
        import json
        logger.info(
            "webhook.payload.received",
            full_payload=json.dumps(payload, indent=2, default=str),
        )

        # Return 200 immediately, process async
        if self.event_handler:
            asyncio.create_task(self._process_webhook(payload))

        return web.json_response({"status": "received"})

    async def _process_webhook(self, payload: dict[str, Any]) -> None:
        """Process webhook payload asynchronously.

        Args:
            payload: Parsed webhook JSON payload
        """
        try:
            if self.event_handler:
                await self.event_handler.handle_event(payload)
        except Exception as e:
            logger.error("webhook.process.failed", error=str(e), exc_info=True)
