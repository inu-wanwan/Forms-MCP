"""forms.responses リソース: get / list"""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp_types import ToolAnnotations
from pydantic import Field

from forms_mcp.errors import execute, get_service
from forms_mcp.google_clients import GoogleServices
from forms_mcp.tools.forms import FormId


def register(mcp: MCPServer, services: GoogleServices) -> None:
    @mcp.tool(annotations=ToolAnnotations(title="回答を 1 件取得", read_only_hint=True))
    def get_response(
        form_id: FormId,
        response_id: Annotated[str, Field(description="回答 ID（list_responses の responses[].responseId）")],
    ) -> dict[str, Any]:
        """フォームの回答を 1 件取得する（forms.responses.get）。

        戻り値の answers は questionId をキーとする辞書。どの質問の回答かは get_form の
        items[].questionItem.question.questionId と突き合わせて判断する。
        テキスト回答は textAnswers.answers[].value、ファイルアップロードは fileUploadAnswers、
        テストの採点結果は grade に入る。respondentEmail はメール収集が有効な場合のみ含まれる。
        """
        forms = get_service(services.forms)
        return execute(
            forms.forms().responses().get(formId=form_id, responseId=response_id), "forms.responses.get"
        )

    @mcp.tool(annotations=ToolAnnotations(title="回答を一覧取得", read_only_hint=True))
    def list_responses(
        form_id: FormId,
        filter: Annotated[
            str | None,
            Field(
                description=(
                    "回答の絞り込み条件。対応しているのは提出時刻のみで、書式は "
                    "'timestamp > 2025-01-01T00:00:00Z' または 'timestamp >= 2025-01-01T00:00:00Z'（RFC3339、UTC 推奨）"
                )
            ),
        ] = None,
        page_size: Annotated[
            int | None, Field(description="1 ページの最大件数（上限 5000。省略時は最大 5000 件）", ge=1, le=5000)
        ] = None,
        page_token: Annotated[str | None, Field(description="前回の結果の nextPageToken。続きのページを取得する")] = None,
    ) -> dict[str, Any]:
        """フォームの回答を一覧取得する（forms.responses.list）。

        戻り値: responses（回答の配列。各要素の形式は get_response と同じ）と、続きがある場合は nextPageToken。
        回答が 0 件の場合は responses キー自体が含まれないことがある。
        特定時刻以降の新着だけ取りたい場合は filter で timestamp 条件を指定する。
        """
        params: dict[str, Any] = {"formId": form_id}
        if filter:
            params["filter"] = filter
        if page_size is not None:
            params["pageSize"] = page_size
        if page_token:
            params["pageToken"] = page_token
        forms = get_service(services.forms)
        return execute(forms.forms().responses().list(**params), "forms.responses.list")
