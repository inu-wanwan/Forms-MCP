"""forms.watches リソース: create / list / renew / delete（Cloud Pub/Sub 通知）"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic import Field

from forms_mcp.errors import execute, get_service
from forms_mcp.google_clients import GoogleServices
from forms_mcp.tools.forms import FormId

WatchId = Annotated[str, Field(description="watch ID（create_watch / list_watches の結果の id）")]


def register(mcp: MCPServer, services: GoogleServices, default_topic: str | None) -> None:
    @mcp.tool(annotations=ToolAnnotations(title="通知 watch を作成", read_only_hint=False, destructive_hint=False))
    def create_watch(
        form_id: FormId,
        event_type: Annotated[
            Literal["SCHEMA", "RESPONSES"],
            Field(description="SCHEMA: フォームの内容・設定が変更されたとき / RESPONSES: 回答が送信されたとき"),
        ],
        topic_name: Annotated[
            str | None,
            Field(description="通知先の Pub/Sub トピック（projects/<project>/topics/<topic>）。省略時はサーバーの PUBSUB_TOPIC を使う"),
        ] = None,
        watch_id: Annotated[
            str | None, Field(description="watch ID を自分で指定する場合（英小文字で始まる 4〜63 文字の英小文字・数字・ハイフン）。省略時は自動採番")
        ] = None,
    ) -> dict[str, Any]:
        """フォームの変更・回答送信を Cloud Pub/Sub に通知する watch を作成する（forms.watches.create）。

        注意:
        - watch は作成から 7 日で失効する。継続する場合は期限前に renew_watch で延長すること。
        - Pub/Sub トピックには forms-notifications@system.gserviceaccount.com に
          「Pub/Sub パブリッシャー」ロールを付与しておく必要がある。
        - 通知には回答の中身は含まれない（formId と eventType のみ）。内容は get_form / list_responses で取得する。
        - 同じフォームに作れる watch の数には上限がある。不要になったら delete_watch で削除する。
        戻り値: 作成された Watch（id、state、expireTime など）。
        """
        topic = topic_name or default_topic
        if not topic:
            raise ToolError(
                "Pub/Sub トピックが指定されていません。topic_name 引数に 'projects/<project>/topics/<topic>' を渡すか、"
                "サーバーの環境変数 PUBSUB_TOPIC を設定してください。"
            )
        body: dict[str, Any] = {"watch": {"target": {"topic": {"topicName": topic}}, "eventType": event_type}}
        if watch_id:
            body["watchId"] = watch_id
        forms = get_service(services.forms)
        return execute(forms.forms().watches().create(formId=form_id, body=body), "forms.watches.create")

    @mcp.tool(annotations=ToolAnnotations(title="通知 watch を一覧", read_only_hint=True))
    def list_watches(form_id: FormId) -> dict[str, Any]:
        """フォームに設定されている watch を一覧する（forms.watches.list）。

        このアプリ（OAuth クライアントの Cloud プロジェクト）が作成した watch だけが返る。
        各 watch の state（ACTIVE / SUSPENDED）、errorType、expireTime を確認できる。
        """
        forms = get_service(services.forms)
        return execute(forms.forms().watches().list(formId=form_id), "forms.watches.list")

    @mcp.tool(annotations=ToolAnnotations(title="通知 watch を延長", read_only_hint=False, idempotent_hint=True))
    def renew_watch(form_id: FormId, watch_id: WatchId) -> dict[str, Any]:
        """watch の有効期限を作成時と同じ期間（7 日）だけ延長する（forms.watches.renew）。

        戻り値: 更新後の Watch（新しい expireTime を含む）。
        """
        forms = get_service(services.forms)
        return execute(
            forms.forms().watches().renew(formId=form_id, watchId=watch_id, body={}), "forms.watches.renew"
        )

    @mcp.tool(annotations=ToolAnnotations(title="通知 watch を削除", read_only_hint=False, destructive_hint=True))
    def delete_watch(form_id: FormId, watch_id: WatchId) -> dict[str, Any]:
        """watch を削除して通知を止める（forms.watches.delete）。フォームや回答には影響しない。"""
        forms = get_service(services.forms)
        execute(forms.forms().watches().delete(formId=form_id, watchId=watch_id), "forms.watches.delete")
        return {"deleted": True, "form_id": form_id, "watch_id": watch_id}
