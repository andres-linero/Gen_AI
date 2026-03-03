"""
aiohttp Server Bootstrap for Teams Bot
Handles incoming webhook messages from Azure Bot Service.
"""

from os import environ

from aiohttp.web import Request, Response, Application, run_app

from microsoft_agents.hosting.aiohttp import (
    start_agent_process,
    jwt_authorization_middleware,
    CloudAdapter,
)
from microsoft_agents.hosting.core import AgentApplication, AgentAuthConfiguration


def start_server(
    agent_application: AgentApplication,
    auth_configuration=None,
):
    """Start the aiohttp web server. Uses JWT middleware in production,
    plain server in local dev mode."""

    async def messages(req: Request) -> Response:
        """POST /api/messages - Teams webhook endpoint."""
        agent: AgentApplication = req.app["agent_app"]
        adapter: CloudAdapter = req.app["adapter"]
        return await start_agent_process(req, agent, adapter)

    async def health(req: Request) -> Response:
        """GET /api/messages - Health check."""
        return Response(status=200, text="OK")

    # Only use JWT middleware when auth is configured (production)
    middlewares = [jwt_authorization_middleware] if auth_configuration else []
    app = Application(middlewares=middlewares)
    app.router.add_post("/api/messages", messages)
    app.router.add_get("/api/messages", health)
    app["agent_configuration"] = auth_configuration
    app["agent_app"] = agent_application
    app["adapter"] = agent_application.adapter

    port = int(environ.get("PORT", 3978))
    print(f"Bot server starting on http://0.0.0.0:{port}/api/messages")

    try:
        run_app(app, host="0.0.0.0", port=port)
    except Exception as error:
        raise error
