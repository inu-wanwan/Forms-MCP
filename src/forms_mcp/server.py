"""MCPServer の生成。"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from forms_mcp.google_clients import GoogleServices
from forms_mcp.tools import register_all

INSTRUCTIONS = """\
Google Forms を作成・編集・参照するためのツール群です。
- 新規作成: create_form（タイトルのみ）→ batch_update で説明・質問・設定を追加 → 必要なら set_publish_settings。
- 既存フォームの編集: 先に get_form で itemId / index / revisionId を確認してから batch_update。
- 回答の集計: get_form で questionId と質問文の対応を取り、list_responses の answers と突き合わせる。
- フォーム一覧（list_forms）はこのアプリで作成・複製したフォームだけが対象（drive.file スコープの制約）。
"""


def create_mcp_server(services: GoogleServices, *, pubsub_topic: str | None = None) -> MCPServer:
    mcp = MCPServer(name="google-forms", title="Google Forms", instructions=INSTRUCTIONS)
    register_all(mcp, services, pubsub_topic=pubsub_topic)
    return mcp
