"""ASGI アプリとエントリポイント。

公開するのは次の 2 つだけで、それ以外はすべて 404:
- GET /healthz
- /mcp/<MCP_PATH_SECRET>（Streamable HTTP、stateless）

起動: uv run python -m forms_mcp.app
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp

from forms_mcp.auth.google_credentials import RefreshTokenCredentialsProvider
from forms_mcp.auth.path_secret import PathSecretDispatcher, SecretRedactingFilter
from forms_mcp.config import Settings, load_settings
from forms_mcp.google_clients import DefaultGoogleServices, GoogleServices
from forms_mcp.server import create_mcp_server

logger = logging.getLogger("forms_mcp")


async def healthz(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


def build_app(settings: Settings, services: GoogleServices | None = None) -> tuple[ASGIApp, MCPServer]:
    if services is None:
        services = DefaultGoogleServices(RefreshTokenCredentialsProvider(settings.google))
    mcp = create_mcp_server(services, pubsub_topic=settings.pubsub_topic)

    mcp_app = mcp.streamable_http_app(
        streamable_http_path="/",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=list(settings.allowed_hosts),
            allowed_origins=list(settings.allowed_origins),
        ),
    )

    # mount した MCP アプリの lifespan は実行されないため、外側のアプリで session manager を起動する
    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with mcp.session_manager.run():
            yield

    fallback = Starlette(routes=[Route("/healthz", healthz, methods=["GET", "HEAD"])], lifespan=lifespan)
    app = PathSecretDispatcher(secret=settings.path_secret, mcp_app=mcp_app, fallback=fallback)
    return app, mcp


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = load_settings()

    # ハンドラに付けることで、全ロガー（uvicorn.access など）から来たレコードでシークレットを伏せる
    redactor = SecretRedactingFilter(settings.path_secret)
    for handler in logging.getLogger().handlers:
        handler.addFilter(redactor)

    if settings.google is None:
        logger.warning("Google の認証情報が未設定です。ツール一覧は取得できますが、API 呼び出しはエラーになります。")
    logger.info("allowed hosts: %s", ", ".join(settings.allowed_hosts))
    logger.info("MCP endpoint: /mcp/*** (secret is not logged)")

    app, _ = build_app(settings)
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        proxy_headers=True,
        forwarded_allow_ips="*",
        log_config=None,  # basicConfig のハンドラを使い、上で付けたフィルタを有効にする
    )


if __name__ == "__main__":
    main()
