"""認証まわり。

- Google API 側: `CredentialsProvider` が Google の認証情報を返す。
  第1段階は環境変数のリフレッシュトークンを使う `RefreshTokenCredentialsProvider`。
  将来 MCP 仕様準拠の OAuth（このサーバーが認可サーバーとなり Google ログインを仲介）に移行する場合は、
  リクエストごとのユーザーに紐づく認証情報を返す実装に差し替える。
- Claude → サーバー側: `path_secret` が推測不能なパスでエンドポイントを隠す。
  OAuth 移行時は `MCPServer.streamable_http_app(auth=...)` に置き換えて、この層は外す。
"""

from typing import Protocol

from google.auth.credentials import Credentials


class CredentialsProvider(Protocol):
    def get_credentials(self) -> Credentials:
        """Google API 呼び出しに使う認証情報を返す。"""
        ...


class MissingCredentialsError(RuntimeError):
    """Google の認証情報が設定されていない。"""
