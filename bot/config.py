"""
Bot Configuration
Loads all environment variables for the Teams bot and SkyTrac agent.
"""

import os
from dotenv import load_dotenv

# Load .env from project root (single source of truth)
_bot_dir = os.path.dirname(__file__)
_project_root = os.path.join(_bot_dir, "..")
load_dotenv(os.path.join(_project_root, ".env"))


class BotConfig:
    """Single source of truth for all configuration."""

    # Azure Bot / Teams identity (Single Tenant)
    # Supports both naming conventions (yours and the SDK default)
    CLIENT_ID = os.environ.get("MICROSOFT_APP_ID", "") or os.environ.get("CLIENT_ID", "")
    CLIENT_SECRET = os.environ.get("MICROSOFT_APP_PASSWORD", "") or os.environ.get("CLIENT_SECRET", "")
    TENANT_ID = os.environ.get("MICROSOFT_APP_TENANT_ID", "") or os.environ.get("TENANT_ID", "")

    # Server
    PORT = int(os.environ.get("PORT", 3978))

    # Security
    MAX_MESSAGE_LENGTH = 1000
    RATE_LIMIT_PER_MINUTE = 20

    # Agent config (passed through to SkyTracAgent via env vars)
    CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "")
    EXCEL_PATH = os.environ.get("EXCEL_PATH", "")
