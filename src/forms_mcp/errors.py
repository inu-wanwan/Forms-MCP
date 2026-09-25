"""Google API 呼び出しの実行とエラー整形。

HttpError などを握りつぶさず、HTTP ステータス・Google のエラーメッセージ・考えられる原因を
Claude が読める形の ToolError に変換する。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from google.auth.exceptions import RefreshError, TransportError
from googleapiclient.errors import HttpError
from mcp.server.mcpserver.exceptions import ToolError

from forms_mcp.auth import MissingCredentialsError

logger = logging.getLogger(__name__)

SCOPE_HINT = (
    "OAuth スコープ不足の可能性があります。scripts/get_refresh_token.py でリフレッシュトークンを取り直し、"
    "forms.body / forms.responses.readonly / drive.file の 3 つが付与されているか確認してください。"
)


def _parse_http_error(err: HttpError) -> tuple[int, str, str]:
    """(status, google_status, message) を取り出す。"""
    status = int(getattr(err.resp, "status", 0) or 0)
    google_status = ""
    message = ""
    try:
        payload = json.loads(err.content.decode("utf-8") if isinstance(err.content, bytes) else err.content)
        error = payload.get("error", {}) if isinstance(payload, dict) else {}
        if isinstance(error, dict):
            google_status = str(error.get("status", ""))
            message = str(error.get("message", ""))
        elif isinstance(error, str):
            # OAuth 系のエラーは {"error": "invalid_grant", "error_description": "..."} 形式
            google_status = error
            message = str(payload.get("error_description", ""))
    except (ValueError, AttributeError, UnicodeDecodeError):
        pass
    if not message:
        message = err.reason or str(err)
    return status, google_status, message


def _hints(status: int, google_status: str, message: str, operation: str) -> list[str]:
    msg = message.lower()
    hints: list[str] = []

    if status == 400:
        if "mask" in msg:
            hints.append(
                "updateMask の指定漏れ・誤りの可能性があります。updateItem / updateFormInfo / updateSettings では "
                "updateMask が必須です（例: \"title\", \"description\", \"quizSettings.isQuiz\"、全フィールドなら \"*\"）。"
            )
        if "index" in msg or "location" in msg or "out of" in msg:
            hints.append("location.index がフォームのアイテム数の範囲外の可能性があります。get_form で現在の index を確認してください。")
        if "revision" in msg:
            hints.append("writeControl のリビジョン ID が古い可能性があります。get_form で最新の revisionId を取得し直してください。")
        if "topic" in msg or "pub/sub" in msg or "pubsub" in msg:
            hints.append(
                "Pub/Sub トピック名の形式（projects/<project>/topics/<topic>）や、"
                "forms-notifications@system.gserviceaccount.com への Pub/Sub パブリッシャー権限を確認してください。"
            )
        if "filter" in msg:
            hints.append("filter の書式を確認してください（例: timestamp > 2025-01-01T00:00:00Z）。")
        if not hints:
            hints.append("リクエストの JSON 構造・フィールド名（camelCase）・値の型を確認してください。")
    elif status == 401:
        hints.append("認証情報が無効です。リフレッシュトークンが失効・取り消しされていないか確認し、必要なら取り直してください。")
    elif status == 403:
        if "scope" in msg or "insufficient" in msg:
            hints.append(SCOPE_HINT)
        elif "has not been used" in msg or "disabled" in msg or google_status == "SERVICE_DISABLED":
            hints.append("Google Cloud プロジェクトで該当 API（Forms API / Drive API）が有効になっていない可能性があります。")
        elif "rate" in msg or "quota" in msg:
            hints.append("API のクォータ・レート制限に達しています。時間をおいて再試行してください。")
        else:
            hints.append("認証中の Google アカウントにこのフォームの編集（または閲覧）権限がない可能性があります。")
            hints.append(SCOPE_HINT)
    elif status == 404:
        hints.append("ID が間違っているか、フォーム（または回答・watch）が存在しない・削除済みの可能性があります。")
        hints.append(
            "drive.file スコープでは、このアプリで作成したファイルか、このアプリで開いたファイルにしか Drive API でアクセスできません。"
        )
    elif status == 409:
        hints.append("リソースが競合しています（同じ watchId が既に存在する等）。")
    elif status == 429:
        hints.append("API のレート制限に達しました。時間をおいて再試行してください。")
    elif status >= 500:
        hints.append("Google 側の一時的な障害の可能性があります。時間をおいて再試行してください。")

    if operation == "forms.batchUpdate":
        hints.append("batchUpdate は 1 つでも失敗すると全リクエストがロールバックされるため、フォームは変更されていません。")
    return hints


def format_http_error(err: HttpError, operation: str) -> str:
    status, google_status, message = _parse_http_error(err)
    head = f"Google API エラー（{operation}）: HTTP {status}"
    if google_status:
        head += f" {google_status}"
    lines = [head, f"メッセージ: {message}"]
    hints = _hints(status, google_status, message, operation)
    if hints:
        lines.append("考えられる原因:")
        lines += [f"- {h}" for h in hints]
    return "\n".join(lines)


def execute(request: Any, operation: str) -> dict[str, Any]:
    """googleapiclient の HttpRequest を実行し、失敗時は整形済みの ToolError を送出する。"""
    try:
        result = request.execute()
    except HttpError as err:
        status, google_status, _ = _parse_http_error(err)
        logger.info("Google API error: operation=%s status=%s %s", operation, status, google_status)
        raise ToolError(format_http_error(err, operation)) from err
    except RefreshError as err:
        logger.info("Google token refresh failed: operation=%s", operation)
        raise ToolError(
            f"Google のアクセストークン更新に失敗しました（{operation}）: {err}\n"
            "考えられる原因:\n"
            "- リフレッシュトークンが失効・取り消しされた（invalid_grant）。OAuth 同意画面が「テスト」状態だと 7 日で失効します。\n"
            "- GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET がトークン取得時のクライアントと一致していない。\n"
            "scripts/get_refresh_token.py でトークンを取り直してください。"
        ) from err
    except TransportError as err:
        raise ToolError(f"Google API への接続に失敗しました（{operation}）: {err}") from err
    return result if isinstance(result, dict) else {}


def get_service(factory: Any) -> Any:
    """services.forms / services.drive を呼び、認証情報未設定を ToolError にする。"""
    try:
        return factory()
    except MissingCredentialsError as err:
        raise ToolError(str(err)) from err
