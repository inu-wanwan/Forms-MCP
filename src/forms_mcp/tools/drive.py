"""Forms API にない操作を Drive API v3（drive.file スコープ）で補う: 一覧 / 複製 / ゴミ箱移動"""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp_types import ToolAnnotations
from pydantic import Field

from forms_mcp.errors import execute, get_service
from forms_mcp.google_clients import GoogleServices
from forms_mcp.scopes import FORMS_MIME_TYPE
from forms_mcp.tools.forms import FormId, edit_url

FILE_FIELDS = "id, name, createdTime, modifiedTime, webViewLink, trashed"


def register(mcp: MCPServer, services: GoogleServices) -> None:
    @mcp.tool(annotations=ToolAnnotations(title="フォームを一覧", read_only_hint=True))
    def list_forms(
        page_size: Annotated[
            int | None, Field(description="1 ページの最大件数（1〜1000。省略時は Drive API の既定値 100）", ge=1, le=1000)
        ] = None,
        page_token: Annotated[str | None, Field(description="前回の結果の nextPageToken。続きのページを取得する")] = None,
    ) -> dict[str, Any]:
        """Google フォームのファイルを最終更新日時の新しい順に一覧する（Drive API files.list）。ゴミ箱のものは除く。

        重要: このサーバーは drive.file スコープのみを使うため、一覧に出るのは
        「このアプリ（同じ OAuth クライアント）で作成・複製したフォーム」などアプリがアクセス権を持つものだけ。
        ブラウザで手動作成したフォームや他のアプリで作ったフォームは表示されない
        （フォーム ID が分かっていれば get_form など Forms API のツールでは操作できる）。

        戻り値: files（id=フォーム ID、name、createdTime、modifiedTime、webViewLink）と、続きがある場合は nextPageToken。
        """
        params: dict[str, Any] = {
            "q": f"mimeType='{FORMS_MIME_TYPE}' and trashed=false",
            "fields": f"nextPageToken, files({FILE_FIELDS})",
            "orderBy": "modifiedTime desc",
        }
        if page_size is not None:
            params["pageSize"] = page_size
        if page_token:
            params["pageToken"] = page_token
        drive = get_service(services.drive)
        return execute(drive.files().list(**params), "drive.files.list")

    @mcp.tool(annotations=ToolAnnotations(title="フォームを複製", read_only_hint=False, destructive_hint=False))
    def copy_form(
        form_id: FormId,
        new_title: Annotated[str, Field(description="複製先の Drive 上のファイル名")],
    ) -> dict[str, Any]:
        """フォームを複製する（Drive API files.copy）。質問・設定はコピーされ、回答はコピーされない。

        new_title は Drive 上のファイル名になる。フォームの表示タイトル（info.title）はコピー元のままなので、
        変える場合は複製後に batch_update の updateFormInfo（updateMask: "title"）を使う。
        drive.file スコープのため、コピー元はこのアプリで作成・複製したフォームである必要がある（それ以外は 404 になる）。

        戻り値: form_id（新しいフォーム ID）、edit_url、file（Drive のファイル情報）。
        """
        drive = get_service(services.drive)
        file = execute(
            drive.files().copy(fileId=form_id, body={"name": new_title}, fields=FILE_FIELDS), "drive.files.copy"
        )
        new_id = file.get("id", "")
        return {"form_id": new_id, "edit_url": edit_url(new_id), "file": file}

    @mcp.tool(annotations=ToolAnnotations(title="フォームをゴミ箱へ移動", read_only_hint=False, destructive_hint=True))
    def trash_form(form_id: FormId) -> dict[str, Any]:
        """フォームを Google ドライブのゴミ箱に移動する（Drive API files.update で trashed=true）。

        完全削除はしない。ゴミ箱のファイルは約 30 日後に自動で完全削除されるが、それまではドライブの画面から復元できる。
        drive.file スコープのため、対象はこのアプリで作成・複製したフォームに限られる（それ以外は 404 になる）。
        """
        drive = get_service(services.drive)
        return execute(
            drive.files().update(fileId=form_id, body={"trashed": True}, fields="id, name, trashed"),
            "drive.files.update",
        )
