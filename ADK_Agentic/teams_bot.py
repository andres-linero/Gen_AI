"""
SkyTrac Teams Bot — Chat Only
Employees can ask questions about work orders via Teams.
No image processing, no channel scanning — all scans run locally.
"""

import os
import json
import time
from typing import Dict
from dotenv import load_dotenv

from aiohttp import web
from botbuilder.core import (
    BotFrameworkAdapter,
    BotFrameworkAdapterSettings,
    TurnContext,
)
from botbuilder.core.integration import aiohttp_error_middleware
from botbuilder.schema import Activity, ActivityTypes

from agent import create_agent_instance
from chat_logger import log_interaction, get_history

load_dotenv()

print("\n" + "=" * 70)
print("SkyTrac Teams Bot")
print("=" * 70)

# Initialize agent
print("\nInitializing SkyTrac Agent...")
try:
    agent = create_agent_instance()
    print("Agent initialized")
except Exception as e:
    print(f"Agent initialization failed: {e}")
    agent = None

# Create adapter
SETTINGS = BotFrameworkAdapterSettings(
    app_id=os.getenv("MICROSOFT_APP_ID", ""),
    app_password=os.getenv("MICROSOFT_APP_PASSWORD", ""),
)

ADAPTER = BotFrameworkAdapter(SETTINGS)

# SkyTrac allowed domains (restrict to company only)
ALLOWED_DOMAINS = [
    "skytracusa.com",
    "skytrac.com",
    "skytracaccess.com",
]


class SkyTracAuth:
    """Verify user is from SkyTrac"""

    @staticmethod
    def is_skytrac_user(email: str) -> bool:
        if not email:
            return False
        domain = email.split("@")[-1].lower()
        return domain in ALLOWED_DOMAINS

    @staticmethod
    def get_user_info(turn_context: TurnContext) -> Dict[str, str]:
        try:
            activity = turn_context.activity
            user_id = activity.from_property.id if activity.from_property else "unknown"
            user_name = activity.from_property.name if activity.from_property else "Unknown"
            email = getattr(activity.from_property, 'email', None) or f"{user_name}@skytracusa.com"
            return {"id": user_id, "name": user_name, "email": email}
        except Exception:
            return {"id": "unknown", "name": "Unknown User", "email": "unknown@skytracusa.com"}


async def messages(req: web.Request) -> web.Response:
    """Handle incoming messages from Teams"""

    try:
        if "application/json" not in req.headers.get("Content-Type", ""):
            return web.Response(status=415, text="Content-Type must be application/json")

        try:
            body = await req.json()
        except json.JSONDecodeError:
            return web.Response(status=400, text="Invalid JSON")

        try:
            activity = Activity().deserialize(body)
        except Exception as e:
            return web.Response(status=400, text=f"Invalid activity: {e}")

        auth_header = req.headers.get("Authorization", "")

        async def turn_handler(turn_context: TurnContext):
            try:
                user_info = SkyTracAuth.get_user_info(turn_context)

                # Verify user is from SkyTrac
                if not SkyTracAuth.is_skytrac_user(user_info['email']):
                    await turn_context.send_activity(
                        "Access denied. This bot is for SkyTrac employees only."
                    )
                    return

                if turn_context.activity.type == ActivityTypes.message:
                    user_input = turn_context.activity.text or ""

                    if not agent:
                        response = "Agent not initialized. Please try again later."
                    else:
                        try:
                            start_time = time.time()
                            history = get_history(user_info["id"])
                            response = agent.query(user_input, history=history)
                            duration_ms = (time.time() - start_time) * 1000

                            try:
                                log_interaction(
                                    user_id=user_info["id"],
                                    user_name=user_info["name"],
                                    email=user_info["email"],
                                    user_input=user_input,
                                    response=response,
                                    interaction_type="query",
                                    duration_ms=duration_ms,
                                )
                            except Exception:
                                pass

                        except Exception as e:
                            response = f"Error processing request: {str(e)}"

                    try:
                        await turn_context.send_activity(response)
                    except Exception:
                        pass

                elif turn_context.activity.type == ActivityTypes.conversation_update:
                    if turn_context.activity.members_added:
                        for member in turn_context.activity.members_added:
                            if member.id != turn_context.activity.recipient.id:
                                await turn_context.send_activity(
                                    "Welcome to SkyTrac Agent!\n\n"
                                    "I can help you look up work orders, check status, "
                                    "and find order details.\n\n"
                                    "Try: 'Show me all orders' or 'Details for W-108624'"
                                )

            except Exception as e:
                import traceback
                traceback.print_exc()

        await ADAPTER.process_activity(activity, auth_header, turn_handler)
        return web.Response(status=200)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return web.Response(status=500, text=str(e))


async def health(req: web.Request) -> web.Response:
    return web.Response(text="OK", status=200)


async def create_app():
    app = web.Application(middlewares=[aiohttp_error_middleware])
    app.router.add_post("/api/messages", messages)
    app.router.add_get("/health", health)
    return app


if __name__ == "__main__":
    import asyncio

    print(f"\nApp ID: {os.getenv('MICROSOFT_APP_ID', 'NOT SET')[:20]}...")
    print(f"Listening on: http://0.0.0.0:3978")
    print(f"Endpoint: /api/messages")
    print(f"Security: SkyTrac domain only (@skytracusa.com, @skytrac.com)")

    app = asyncio.run(create_app())
    web.run_app(app, host="0.0.0.0", port=3978)
