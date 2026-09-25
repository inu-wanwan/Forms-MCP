"""環境変数からの設定読み込み。

シークレットを含むフィールドは repr=False にして、設定オブジェクトをログに出しても値が漏れないようにしている。
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

MIN_PATH_SECRET_LENGTH = 32

# claude.ai のカスタムコネクタはサーバー側から接続するため通常 Origin ヘッダは付かないが、
# 付いた場合に 403 で弾かないよう許可しておく。
DEFAULT_ALLOWED_ORIGINS = (
    "https://claude.ai",
    "https://claude.com",
    "http://localhost:*",
    "http://127.0.0.1:*",
)
LOCAL_HOSTS = ("localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*", "[::1]:*")


class ConfigError(RuntimeError):
    """設定が不足・不正なときに送出する。"""


@dataclass(frozen=True)
class GoogleOAuthConfig:
    client_id: str
    client_secret: str = field(repr=False)
    refresh_token: str = field(repr=False)


@dataclass(frozen=True)
class Settings:
    path_secret: str = field(repr=False)
    host: str
    port: int
    allowed_hosts: tuple[str, ...]
    allowed_origins: tuple[str, ...]
    google: GoogleOAuthConfig | None
    pubsub_topic: str | None


def _split_csv(value: str | None) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def load_google_config(env: Mapping[str, str] | None = None) -> GoogleOAuthConfig | None:
    """Google の OAuth 設定を読む。3 つとも未設定なら None、一部だけなら ConfigError。"""
    env = os.environ if env is None else env
    keys = ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN")
    values = {k: env.get(k, "").strip() for k in keys}
    if not any(values.values()):
        return None
    missing = [k for k, v in values.items() if not v]
    if missing:
        raise ConfigError(f"Google 認証の環境変数が不足しています: {', '.join(missing)}")
    return GoogleOAuthConfig(
        client_id=values["GOOGLE_CLIENT_ID"],
        client_secret=values["GOOGLE_CLIENT_SECRET"],
        refresh_token=values["GOOGLE_REFRESH_TOKEN"],
    )


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if env is None else env

    path_secret = env.get("MCP_PATH_SECRET", "").strip()
    if not path_secret:
        raise ConfigError("MCP_PATH_SECRET が設定されていません。README の生成コマンドで作成してください。")
    if len(path_secret) < MIN_PATH_SECRET_LENGTH:
        raise ConfigError(f"MCP_PATH_SECRET は {MIN_PATH_SECRET_LENGTH} 文字以上にしてください。")
    if "/" in path_secret or "?" in path_secret or "#" in path_secret:
        raise ConfigError("MCP_PATH_SECRET に '/', '?', '#' は使えません。")

    hosts = list(LOCAL_HOSTS)
    hosts += _split_csv(env.get("ALLOWED_HOSTS"))
    # Render が自動で設定する公開ホスト名（例: forms-mcp.onrender.com）
    if render_host := env.get("RENDER_EXTERNAL_HOSTNAME", "").strip():
        hosts.append(render_host)

    origins = list(DEFAULT_ALLOWED_ORIGINS)
    origins += [f"https://{h}" for h in hosts if h not in LOCAL_HOSTS]
    origins += _split_csv(env.get("ALLOWED_ORIGINS"))

    return Settings(
        path_secret=path_secret,
        host=env.get("HOST", "0.0.0.0"),
        port=int(env.get("PORT", "8000")),
        allowed_hosts=tuple(dict.fromkeys(hosts)),
        allowed_origins=tuple(dict.fromkeys(origins)),
        google=load_google_config(env),
        pubsub_topic=env.get("PUBSUB_TOPIC", "").strip() or None,
    )
