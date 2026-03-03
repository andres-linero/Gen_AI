"""
SkyTrac Teams Bot Application
Bridges the existing SkyTracAgent (sync, CLI) to Microsoft Teams via the
Microsoft 365 Agents SDK.
"""

import sys
import os
import asyncio
import logging

# Add ADK_Agentic to Python path so we can import the existing agent
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ADK_Agentic"))

from microsoft_agents.hosting.core import (  # noqa: E402
    AgentApplication,
    TurnState,
    TurnContext,
    MemoryStorage,
)
from microsoft_agents.hosting.aiohttp import CloudAdapter  # noqa: E402
from microsoft_agents.authentication.msal import MsalConnectionManager  # noqa: E402

from config import BotConfig  # noqa: E402
from security import run_security_checks, log_request, hash_message  # noqa: E402
from start_server import start_server  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Max characters per Teams message
TEAMS_MESSAGE_LIMIT = 4000

# ---------------------------------------------------------------------------
# SkyTrac Agent singleton (lazy init — expensive to create)
# ---------------------------------------------------------------------------
_skytrac_agent = None


def _get_agent():
    """Initialize the SkyTracAgent once on first use."""
    global _skytrac_agent
    if _skytrac_agent is None:
        from agent import create_agent_instance

        logger.info("Initializing SkyTracAgent...")
        _skytrac_agent = create_agent_instance()
        logger.info("SkyTracAgent ready.")
    return _skytrac_agent


# ---------------------------------------------------------------------------
# Azure Bot / Teams adapter setup
# ---------------------------------------------------------------------------
config = BotConfig()

# If Azure credentials are set, try authenticated mode (production).
# Falls back to local dev mode if credentials are missing or invalid.
adapter = None
auth_config = None

if config.CLIENT_ID and config.CLIENT_SECRET and config.TENANT_ID:
    try:
        logger.info("Attempting PRODUCTION mode (Single Tenant auth)...")
        connection_manager = MsalConnectionManager(
            client_id=config.CLIENT_ID,
            client_secret=config.CLIENT_SECRET,
            tenant_id=config.TENANT_ID,
        )
        adapter = CloudAdapter(connection_manager=connection_manager)
        auth_config = connection_manager.get_default_connection_configuration()
        logger.info("PRODUCTION mode active.")
    except Exception as e:
        logger.warning(f"Azure auth failed ({type(e).__name__}): {e}")
        logger.warning("Falling back to LOCAL DEV mode.")
        adapter = None

if adapter is None:
    logger.warning(
        "Running in LOCAL DEV mode (no Azure auth). "
        "Set MICROSOFT_APP_ID, MICROSOFT_APP_PASSWORD, MICROSOFT_APP_TENANT_ID for production."
    )
    adapter = CloudAdapter()
    auth_config = None

app = AgentApplication[TurnState](
    storage=MemoryStorage(),
    adapter=adapter,
)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------
@app.conversation_update("membersAdded")
async def on_welcome(context: TurnContext, _state: TurnState):
    """Send a welcome message when the bot is added to a conversation."""
    await context.send_activity(
        "Hello! I'm the SkyTrac Work Order Assistant.\n\n"
        "You can ask me things like:\n"
        "- *Show me all orders*\n"
        "- *Details for WO-12345*\n"
        "- *Search orders for customer ABC*\n\n"
        "Type **/help** for more options."
    )


@app.message("/help")
async def on_help(context: TurnContext, _state: TurnState):
    """Respond to /help command."""
    await context.send_activity(
        "**SkyTrac Work Order Assistant**\n\n"
        "I can help you with:\n"
        "- **Search** work orders by keyword, customer, status, date\n"
        "- **Get details** for a specific order (e.g. *details for WO-001*)\n"
        "- **List orders** to see a summary\n\n"
        "Just type your question naturally!"
    )


@app.activity("message")
async def on_message(context: TurnContext, _state: TurnState):
    """Main message handler — runs security checks, then delegates to agent."""
    user_text = context.activity.text
    if not user_text:
        return

    # Extract user/tenant info for security checks
    user_id = getattr(context.activity.from_property, "id", "unknown")
    tenant_id = getattr(
        getattr(context.activity, "channel_data", None), "tenant", {}).get(
        "id", config.TENANT_ID
    ) if hasattr(context.activity, "channel_data") and context.activity.channel_data else config.TENANT_ID

    # --- Security checks ---
    sanitized, rejection = run_security_checks(
        text=user_text,
        user_id=user_id,
        tenant_id=tenant_id,
        max_length=config.MAX_MESSAGE_LENGTH,
    )

    if rejection:
        await context.send_activity(rejection)
        return

    # --- Typing indicator ---
    await context.send_activity({"type": "typing"})

    # --- Run the agent (sync → async bridge) ---
    try:
        agent = _get_agent()
        response = await asyncio.to_thread(agent.query, sanitized)

        # Chunk if response exceeds Teams limit
        if len(response) > TEAMS_MESSAGE_LIMIT:
            for i in range(0, len(response), TEAMS_MESSAGE_LIMIT):
                await context.send_activity(response[i : i + TEAMS_MESSAGE_LIMIT])
        else:
            await context.send_activity(response)

        log_request(
            user_id, tenant_id, hash_message(user_text), "SUCCESS"
        )

    except Exception as e:
        logger.error("Error processing query", exc_info=True)
        log_request(
            user_id, tenant_id, hash_message(user_text), "ERROR", type(e).__name__
        )
        await context.send_activity(
            "I encountered an error processing your request. "
            "Please try again or rephrase your question."
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Try to eagerly initialize the agent so the first message is fast.
    # If it fails (e.g. missing API key), the server still starts and
    # will report the error when a message comes in.
    try:
        _get_agent()
    except Exception as e:
        logger.warning(f"Agent pre-init failed ({type(e).__name__}): {e}")
        logger.warning("Server will start, but queries will fail until config is fixed.")

    try:
        start_server(app, auth_config)
    except Exception as error:
        raise error
