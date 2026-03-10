"""
Teams Channel Scanner
Uses Microsoft Graph API to search channel message history for scanned images,
then OCRs each one via Azure Document Intelligence to extract order numbers.
"""

import os
import logging
from typing import Optional

import aiohttp

from ocr import extract_order_number

logger = logging.getLogger(__name__)


class ChannelScanner:
    """Searches a Teams channel for scanned order documents."""

    GRAPH_BASE = "https://graph.microsoft.com/v1.0"

    def __init__(self):
        self.tenant_id = os.getenv("MICROSOFT_TENANT_ID")
        self.app_id = os.getenv("MICROSOFT_APP_ID")
        self.app_password = os.getenv("MICROSOFT_APP_PASSWORD")
        self.team_id = os.getenv("TEAMS_TEAM_ID")
        self.channel_id = os.getenv("TEAMS_CHANNEL_ID")

    async def _get_graph_token(self) -> str:
        """Get Microsoft Graph access token via client credentials flow."""
        url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": self.app_id,
            "client_secret": self.app_password,
            "scope": "https://graph.microsoft.com/.default",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data) as resp:
                result = await resp.json()
                if "access_token" not in result:
                    raise RuntimeError(f"Graph token error: {result.get('error_description')}")
                return result["access_token"]

    async def _fetch_channel_messages(self, token: str) -> list:
        """Fetch recent messages from the configured Teams channel."""
        url = (
            f"{self.GRAPH_BASE}/teams/{self.team_id}"
            f"/channels/{self.channel_id}/messages"
            f"?$top=50"
        )
        headers = {"Authorization": f"Bearer {token}"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                data = await resp.json()
                return data.get("value", [])

    async def _download_image(self, url: str, token: str) -> Optional[bytes]:
        """Download image from Graph API URL."""
        headers = {"Authorization": f"Bearer {token}"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    return await resp.read()
                logger.warning(f"Image download failed: {resp.status} {url}")
                return None

    async def find_scan_for_order(self, order_id: str) -> Optional[str]:
        """
        Search the Teams channel for a scanned image matching the given order_id.
        Returns the extracted order number if found, None otherwise.
        """
        if not all([self.tenant_id, self.app_id, self.app_password, self.team_id, self.channel_id]):
            raise RuntimeError(
                "Missing env vars: MICROSOFT_TENANT_ID, TEAMS_TEAM_ID, TEAMS_CHANNEL_ID required."
            )

        logger.info(f"Searching channel for scan matching order: {order_id}")
        token = await self._get_graph_token()
        messages = await self._fetch_channel_messages(token)

        for msg in messages:
            attachments = msg.get("attachments", [])
            for att in attachments:
                content_type = att.get("contentType", "")
                if "image" not in content_type and not att.get("name", "").lower().endswith(
                    (".jpg", ".jpeg", ".png", ".gif", ".webp")
                ):
                    continue

                # Graph attachment URL
                content_url = att.get("contentUrl") or att.get("content")
                if not content_url:
                    continue

                logger.info(f"Checking attachment: {att.get('name')}")
                image_bytes = await self._download_image(content_url, token)
                if not image_bytes:
                    continue

                extracted = extract_order_number(image_bytes)
                logger.info(f"OCR result: {extracted}")

                # Match: exact or partial (e.g. "18465" matches "18465.0")
                if extracted and (
                    extracted == order_id
                    or order_id in extracted
                    or extracted in order_id
                ):
                    return extracted

        return None
