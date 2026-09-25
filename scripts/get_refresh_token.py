"""Google OAuth のリフレッシュトークンを取得するローカル用スクリプト。

ブラウザで Google にログインして同意すると、GOOGLE_REFRESH_TOKEN に設定する値を表示する。
付与されたスコープが forms_mcp.scopes.SCOPES と一致するかも検証する。

使い方（どちらか）:
    uv run python scripts/get_refresh_token.py --client-secrets client_secret_xxx.json
    GOOGLE_CLIENT_ID=... GOOGLE_CLIENT_SECRET=... uv run python scripts/get_refresh_token.py

OAuth クライアントは「デスクトップアプリ」タイプを使うこと。
"""

from __future__ import annotations

import argparse
import os
import sys

# 付与スコープが要求と違っても oauthlib に例外を出させず、下で自前で検証する
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: E402

from forms_mcp.scopes import SCOPES  # noqa: E402


def build_flow(client_secrets: str | None) -> InstalledAppFlow:
    if client_secrets:
        return InstalledAppFlow.from_client_secrets_file(client_secrets, scopes=list(SCOPES))
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        sys.exit("--client-secrets を指定するか、環境変数 GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET を設定してください。")
    config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    return InstalledAppFlow.from_client_config(config, scopes=list(SCOPES))


def main() -> int:
    parser = argparse.ArgumentParser(description="Google Forms MCP 用のリフレッシュトークンを取得する")
    parser.add_argument("--client-secrets", help="Google Cloud からダウンロードした OAuth クライアント JSON のパス")
    parser.add_argument("--port", type=int, default=0, help="ローカルのリダイレクト受け口のポート（0 は空きポートを自動選択）")
    parser.add_argument("--no-browser", action="store_true", help="ブラウザを自動で開かず URL を表示するだけにする")
    args = parser.parse_args()

    flow = build_flow(args.client_secrets)
    # access_type=offline と prompt=consent で、毎回確実にリフレッシュトークンを発行させる
    creds = flow.run_local_server(
        port=args.port,
        open_browser=not args.no_browser,
        access_type="offline",
        prompt="consent",
    )

    if not creds.refresh_token:
        print("エラー: リフレッシュトークンが返されませんでした。もう一度実行してください。", file=sys.stderr)
        return 1

    raw_granted = creds.granted_scopes
    if isinstance(raw_granted, str):
        raw_granted = raw_granted.split()
    granted = set(raw_granted or [])
    missing = [s for s in SCOPES if s not in granted]

    print()
    print("=" * 72)
    print("GOOGLE_REFRESH_TOKEN に次の値を設定してください（他人に共有しないこと）:")
    print()
    print(creds.refresh_token)
    print("=" * 72)
    print("付与されたスコープ:")
    for scope in sorted(granted):
        print(f"  - {scope}")

    if missing:
        print(file=sys.stderr)
        print("警告: 次のスコープが付与されていません。同意画面ですべてのチェックボックスをオンにして再実行してください:", file=sys.stderr)
        for scope in missing:
            print(f"  - {scope}", file=sys.stderr)
        return 2

    print("OK: 必要な 3 つのスコープがすべて付与されています。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
