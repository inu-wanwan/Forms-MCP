"""推測不能なパス `/mcp/<MCP_PATH_SECRET>` で MCP エンドポイントを公開する ASGI ディスパッチャ。

- `/mcp/<secret>` と `/mcp/<secret>/` だけを MCP アプリに渡す（リダイレクトはしない）
- シークレットの比較は定数時間で行う
- それ以外のパスは fallback アプリ（/healthz と 404 を返す Starlette）に渡す
"""

from __future__ import annotations

import hmac
import logging

from starlette.types import ASGIApp, Receive, Scope, Send

MCP_PREFIX = "/mcp/"


def mcp_path(secret: str) -> str:
    return f"{MCP_PREFIX}{secret}"


class PathSecretDispatcher:
    def __init__(self, *, secret: str, mcp_app: ASGIApp, fallback: ASGIApp) -> None:
        self._secret = secret.encode()
        self._mcp_app = mcp_app
        self._fallback = fallback

    def _matches(self, path: str) -> bool:
        if not path.startswith(MCP_PREFIX):
            return False
        candidate = path[len(MCP_PREFIX) :]
        if candidate.endswith("/"):
            candidate = candidate[:-1]
        return hmac.compare_digest(candidate.encode(), self._secret)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and self._matches(scope["path"]):
            # MCP アプリは streamable_http_path="/" で作成しているので、パスを "/" に書き換えて渡す
            inner = dict(scope)
            inner["path"] = "/"
            inner["raw_path"] = b"/"
            await self._mcp_app(inner, receive, send)
            return
        await self._fallback(scope, receive, send)


class SecretRedactingFilter(logging.Filter):
    """ログ中のシークレット文字列を *** に置き換える（uvicorn のアクセスログ対策）。"""

    def __init__(self, secret: str) -> None:
        super().__init__()
        self._secret = secret

    def _redact(self, value: object) -> object:
        if isinstance(value, str) and self._secret in value:
            return value.replace(self._secret, "***")
        return value

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self._redact(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(self._redact(a) for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: self._redact(v) for k, v in record.args.items()}
        return True
