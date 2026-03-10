"""
SkyTrac Teams Bot - Production Ready
Handles images, authentication, and security for internal use
"""

import os
import json
import time
import aiohttp
from typing import Dict, Optional
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
from ocr import extract_order_number
from chat_logger import log_interaction, get_history

load_dotenv()

print("\n" + "=" * 70)
print("SkyTrac Teams Bot - Production Ready")
print("=" * 70)

# Initialize agent
print("\n🤖 Initializing SkyTrac Agent...")
try:
    agent = create_agent_instance()
    print("✓ Agent initialized")
except Exception as e:
    print(f"✗ Agent initialization failed: {e}")
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
        """Check if user is from SkyTrac domain"""
        if not email:
            return False
        
        domain = email.split("@")[-1].lower()
        return domain in ALLOWED_DOMAINS
    
    @staticmethod
    def get_user_info(turn_context: TurnContext) -> Dict[str, str]:
        """Extract user info from Teams context"""
        try:
            activity = turn_context.activity
            user_id = activity.from_property.id if activity.from_property else "unknown"
            user_name = activity.from_property.name if activity.from_property else "Unknown"
            email = getattr(activity.from_property, 'email', None) or f"{user_name}@skytracusa.com"
            
            return {
                "id": user_id,
                "name": user_name,
                "email": email,
            }
        except Exception as e:
            print(f"⚠ Could not extract user info: {e}")
            return {
                "id": "unknown",
                "name": "Unknown User",
                "email": "unknown@skytracusa.com",
            }


class ImageHandler:
    """Process scanned documents from Teams — OCR via Azure Document Intelligence"""

    @staticmethod
    async def _get_bot_token() -> str:
        """Get bot OAuth token to download Teams-hosted images"""
        from botframework.connector.auth import MicrosoftAppCredentials
        credentials = MicrosoftAppCredentials(
            os.getenv("MICROSOFT_APP_ID", ""),
            os.getenv("MICROSOFT_APP_PASSWORD", ""),
        )
        token = await credentials.get_token()
        return token

    @staticmethod
    async def _download_image(url: str, token: str) -> bytes:
        """Download image bytes from Teams CDN using bot token"""
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers={"Authorization": f"Bearer {token}"}) as resp:
                return await resp.read()

    @staticmethod
    async def process_scan(turn_context: TurnContext) -> Optional[str]:
        """
        Full scan pipeline:
        1. Find image attachment
        2. Download it with bot token
        3. OCR via Azure Document Intelligence → extract order number
        Returns the extracted order number, or None if no image found.
        """
        activity = turn_context.activity
        if not activity.attachments:
            return None

        for attachment in activity.attachments:
            if attachment.content_type and "image" in attachment.content_type:
                print(f"📸 Scan received: {attachment.name}")
                try:
                    token = await ImageHandler._get_bot_token()
                    image_bytes = await ImageHandler._download_image(attachment.content_url, token)
                    order_number = extract_order_number(image_bytes)
                    print(f"🔍 OCR extracted: {order_number}")
                    return order_number
                except Exception as e:
                    print(f"⚠ Scan processing failed: {e}")
                    return None

        return None


async def messages(req: web.Request) -> web.Response:
    """Handle incoming messages from Teams"""
    
    print(f"\n📨 Incoming request: {req.method} {req.path}")
    
    try:
        # Validate content type
        if "application/json" not in req.headers.get("Content-Type", ""):
            return web.Response(status=415, text="Content-Type must be application/json")
        
        # Read request body
        try:
            body = await req.json()
        except json.JSONDecodeError:
            return web.Response(status=400, text="Invalid JSON")
        
        # Deserialize to Activity
        try:
            activity = Activity().deserialize(body)
        except Exception as e:
            print(f"✗ Failed to deserialize activity: {e}")
            return web.Response(status=400, text=f"Invalid activity: {e}")
        
        # Get auth header
        auth_header = req.headers.get("Authorization", "")
        
        # Define turn handler
        async def turn_handler(turn_context: TurnContext):
            """Process the turn"""
            
            print(f"\n🔄 Processing activity: {turn_context.activity.type}")
            
            try:
                # Get user info
                user_info = SkyTracAuth.get_user_info(turn_context)
                print(f"👤 User: {user_info['name']} ({user_info['email']})")
                
                # Verify user is from SkyTrac
                if not SkyTracAuth.is_skytrac_user(user_info['email']):
                    print(f"🚫 Unauthorized user: {user_info['email']}")
                    await turn_context.send_activity(
                        "❌ Access denied. This bot is for SkyTrac employees only.\n\n"
                        "Please contact your administrator if you believe this is an error."
                    )
                    return
                
                if turn_context.activity.type == ActivityTypes.message:
                    user_input = turn_context.activity.text or ""
                    print(f"📝 Message: {user_input}")
                    
                    # Process with agent
                    if not agent:
                        response = "❌ Agent not initialized. Please try again later."
                    else:
                        try:
                            start_time = time.time()

                            # If a scan was attached, run the OCR pipeline
                            order_number = await ImageHandler.process_scan(turn_context)
                            if order_number:
                                order = agent.data_loader.get_order_by_id(order_number)
                                if order:
                                    pdf_name = agent._pdf_name(order)
                                    response = (
                                        f"📄 **Scan matched!**\n\n"
                                        f"{agent._format_record(order)}\n\n"
                                        f"**PDF Name:** `{pdf_name}`"
                                    )
                                else:
                                    response = (
                                        f"📸 Scan read — extracted **{order_number}** — "
                                        f"but no matching order found in the system."
                                    )
                                interaction_type = "scan"
                                effective_input = f"[Image scan] extracted: {order_number}"
                            else:
                                # Text query — load history for context
                                history = get_history(user_info["id"])
                                response = agent.query(user_input, history=history)
                                interaction_type = "query"
                                effective_input = user_input

                            duration_ms = (time.time() - start_time) * 1000

                            # Log the interaction (best-effort)
                            try:
                                log_interaction(
                                    user_id=user_info["id"],
                                    user_name=user_info["name"],
                                    email=user_info["email"],
                                    user_input=effective_input,
                                    response=response,
                                    interaction_type=interaction_type,
                                    duration_ms=duration_ms,
                                )
                            except Exception as log_err:
                                print(f"⚠ Failed to log interaction: {log_err}")

                            print(f"✓ Response sent to {user_info['name']} ({duration_ms:.0f}ms)")
                        except Exception as e:
                            response = f"Error processing request: {str(e)}"
                            print(f"✗ Agent error: {e}")
                    
                    # Send response
                    try:
                        await turn_context.send_activity(response)
                    except Exception as e:
                        print(f"✗ Failed to send response: {e}")
                
                elif turn_context.activity.type == ActivityTypes.conversation_update:
                    # Bot added to conversation
                    if turn_context.activity.members_added:
                        for member in turn_context.activity.members_added:
                            if member.id != turn_context.activity.recipient.id:
                                print(f"👋 Bot added by {member.name}")
                                await turn_context.send_activity(
                                    "👋 **Welcome to SkyTrac Agent!**\n\n"
                                    "I'm your work order assistant. I can help you:\n"
                                    "• 📋 Search for work orders\n"
                                    "• 📝 Find order details\n"
                                    "• 📸 Analyze photos of equipment\n"
                                    "• 📄 Generate work order reports\n\n"
                                    "Try: *'Show me all orders'* or upload a photo!"
                                )
            
            except Exception as e:
                print(f"✗ Error in turn handler: {e}")
                import traceback
                traceback.print_exc()
        
        # Process activity
        print(f"🔄 Processing with adapter...")
        await ADAPTER.process_activity(activity, auth_header, turn_handler)
        
        print(f"✓ Activity processed")
        return web.Response(status=200)
    
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return web.Response(status=500, text=str(e))


async def health(req: web.Request) -> web.Response:
    """Health check endpoint"""
    return web.Response(text="OK", status=200)


async def create_app():
    """Create and configure the web app"""
    app = web.Application(middlewares=[aiohttp_error_middleware])
    
    # Register routes
    app.router.add_post("/api/messages", messages)
    app.router.add_get("/health", health)
    
    print("\n✓ Routes configured")
    return app


if __name__ == "__main__":
    import asyncio
    
    print("\n✅ Configuration:")
    print(f"   App ID: {os.getenv('MICROSOFT_APP_ID', 'NOT SET')[:20]}...")
    print(f"   App Password: {'SET' if os.getenv('MICROSOFT_APP_PASSWORD') else 'NOT SET'}")
    print(f"\n📡 Listening on: http://0.0.0.0:3978")
    print(f"🔗 Endpoint: /api/messages")
    print(f"💚 Health: /health")
    print(f"\n🔒 Security:")
    print(f"   - SkyTrac domain only (@skytracusa.com, @skytrac.com)")
    print(f"   - Image upload ready")
    print(f"   - User authentication enabled")
    print(f"\n⚠️  Make sure ngrok is running:")
    print(f"   ngrok http 3978")
    print("\n" + "=" * 70 + "\n")
    
    app = asyncio.run(create_app())
    web.run_app(app, host="0.0.0.0", port=3978)