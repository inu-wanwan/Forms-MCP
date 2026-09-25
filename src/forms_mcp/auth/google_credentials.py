"""リフレッシュトークンから Google の認証情報を作る（第1段階の簡易構成）。"""

from __future__ import annotations

import threading

from google.oauth2.credentials import Credentials

from forms_mcp.auth import MissingCredentialsError
from forms_mcp.config import GoogleOAuthConfig
from forms_mcp.scopes import SCOPES

TOKEN_URI = "https://oauth2.googleapis.com/token"


class RefreshTokenCredentialsProvider:
    """1 つの Google アカウントのリフレッシュトークンを全リクエストで共有する。

    アクセストークンは google-auth が期限切れ時に自動で更新する。
    """

    def __init__(self, config: GoogleOAuthConfig | None) -> None:
        self._config = config
        self._credentials: Credentials | None = None
        self._lock = threading.Lock()

    def get_credentials(self) -> Credentials:
        if self._config is None:
            raise MissingCredentialsError(
                "Google の認証情報が未設定です。GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / "
                "GOOGLE_REFRESH_TOKEN を環境変数に設定してサーバーを再起動してください。"
            )
        with self._lock:
            if self._credentials is None:
                self._credentials = Credentials(
                    token=None,
                    refresh_token=self._config.refresh_token,
                    client_id=self._config.client_id,
                    client_secret=self._config.client_secret,
                    token_uri=TOKEN_URI,
                    scopes=list(SCOPES),
                )
            return self._credentials
