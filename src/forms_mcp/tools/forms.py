"""forms リソース: create / get / batchUpdate / setPublishSettings"""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic import Field

from forms_mcp.errors import execute, get_service
from forms_mcp.google_clients import GoogleServices

FormId = Annotated[str, Field(description="フォーム ID（編集 URL https://docs.google.com/forms/d/<formId>/edit の <formId> 部分）")]


def edit_url(form_id: str) -> str:
    return f"https://docs.google.com/forms/d/{form_id}/edit"


BATCH_UPDATE_DOC = """\
フォームの内容（質問・説明・設定）を変更する（forms.batchUpdate）。質問の追加・編集・削除・並べ替えはすべてこのツールで行う。

■ 使う前に
- 必ず先に get_form を呼び、対象アイテムの itemId と index（items 配列での 0 始まりの位置）、questionId を確認すること。
  アイテムは itemId ではなく location.index で指定する。
- requests は先頭から順に適用される。前のリクエストで index がずれる点に注意（例: index 0 に挿入すると既存アイテムは +1 される）。
- 1 つでも失敗すると全体がロールバックされ、フォームは一切変更されない。
- updateItem / updateFormInfo / updateSettings では updateMask が必須（カンマ区切りのフィールドパス。全置換は "*"）。
  updateMask に含めたフィールドで値を省略すると、そのフィールドはクリアされる。
- フィールド名は REST API と同じ camelCase で書く。

■ リクエスト種別と最小例（requests 配列の要素。1 要素につきキーは 1 つ）
1. createItem（アイテム追加）
   {"createItem": {"item": {"title": "お名前", "questionItem": {"question": {"required": true, "textQuestion": {"paragraph": false}}}}, "location": {"index": 0}}}
   選択式: {"createItem": {"item": {"title": "満足度", "questionItem": {"question": {"choiceQuestion": {"type": "RADIO", "options": [{"value": "高い"}, {"value": "普通"}, {"value": "低い"}]}}}}, "location": {"index": 1}}}
   （type は RADIO / CHECKBOX / DROP_DOWN。他に scaleQuestion / dateQuestion / timeQuestion / ratingQuestion、
    questionGroupItem（グリッド）、textItem（説明文）、pageBreakItem（セクション区切り）、imageItem、videoItem がある）
2. updateItem（アイテム変更。item 全体ではなく updateMask のフィールドだけが変わる）
   {"updateItem": {"item": {"title": "氏名"}, "location": {"index": 0}, "updateMask": "title"}}
   質問の必須化: {"updateItem": {"item": {"questionItem": {"question": {"required": true}}}, "location": {"index": 0}, "updateMask": "questionItem.question.required"}}
3. deleteItem（アイテム削除）
   {"deleteItem": {"location": {"index": 2}}}
4. moveItem（アイテム移動）
   {"moveItem": {"originalLocation": {"index": 3}, "newLocation": {"index": 0}}}
5. updateFormInfo（タイトル・説明の変更）
   {"updateFormInfo": {"info": {"description": "ご回答ありがとうございます"}, "updateMask": "description"}}
6. updateSettings（フォーム設定の変更）
   テスト（クイズ）化: {"updateSettings": {"settings": {"quizSettings": {"isQuiz": true}}, "updateMask": "quizSettings.isQuiz"}}
   メール収集: {"updateSettings": {"settings": {"emailCollectionType": "VERIFIED"}, "updateMask": "emailCollectionType"}}
   （emailCollectionType は DO_NOT_COLLECT / VERIFIED / RESPONDER_INPUT）

■ リビジョン指定（writeControl。どちらか一方のみ）
- required_revision_id: フォームの現在のリビジョンがこれと一致しないと失敗する（他者の変更を上書きしない厳格モード）。
- target_revision_id: このリビジョン以降の他者の変更と協調的にマージして適用する。
- revisionId は get_form や前回の batch_update の結果（writeControl.requiredRevisionId）で得られる。

■ 戻り値
Google API のレスポンスをそのまま返す: replies（createItem なら作成された itemId と questionId）、
writeControl（更新後のリビジョン）、include_form_in_response=True なら更新後の form 全体。
"""


def register(mcp: MCPServer, services: GoogleServices) -> None:
    @mcp.tool(annotations=ToolAnnotations(title="フォームを作成", read_only_hint=False, destructive_hint=False))
    def create_form(
        title: Annotated[str, Field(description="フォームのタイトル（回答者に表示される）")],
        document_title: Annotated[
            str | None, Field(description="Drive 上のファイル名。省略時は title と同じになる")
        ] = None,
        unpublished: Annotated[
            bool,
            Field(description="True なら未公開（回答を受け付けない）状態で作成する。False または省略時は公開状態で作成される"),
        ] = False,
    ) -> dict[str, Any]:
        """新しい Google フォームを作成する（forms.create）。

        作成時に設定できるのはタイトルと Drive 上のファイル名だけ。説明文・質問・設定は、
        作成後に batch_update（updateFormInfo / createItem / updateSettings）で追加すること。
        公開状態や回答受付は set_publish_settings で後から変更できる。

        戻り値: form_id、edit_url（編集用 URL）、responder_uri（回答用 URL）、revision_id、form（API レスポンス全体）。
        """
        info: dict[str, Any] = {"title": title}
        if document_title:
            info["documentTitle"] = document_title
        forms = get_service(services.forms)
        form = execute(forms.forms().create(body={"info": info}, unpublished=unpublished), "forms.create")
        form_id = form.get("formId", "")
        return {
            "form_id": form_id,
            "edit_url": edit_url(form_id),
            "responder_uri": form.get("responderUri"),
            "revision_id": form.get("revisionId"),
            "form": form,
        }

    @mcp.tool(annotations=ToolAnnotations(title="フォームを取得", read_only_hint=True))
    def get_form(form_id: FormId) -> dict[str, Any]:
        """フォームの全内容を取得する（forms.get）。API のレスポンスを省略せずに返す。

        返る主な内容:
        - info（title / documentTitle / description）、settings（quizSettings / emailCollectionType）
        - items: アイテムの配列。配列内の位置が batch_update で使う location.index（0 始まり）。
          各アイテムの itemId、質問の場合は questionItem.question.questionId（回答データの answers のキー）を含む
        - revisionId（batch_update のリビジョン指定に使う）、responderUri（回答用 URL）、publishSettings、linkedSheetId

        batch_update でアイテムを編集・削除・移動する前に、必ずこのツールで最新の index を確認すること。
        """
        forms = get_service(services.forms)
        return execute(forms.forms().get(formId=form_id), "forms.get")

    @mcp.tool(
        description=BATCH_UPDATE_DOC,
        annotations=ToolAnnotations(title="フォームを一括更新", read_only_hint=False, destructive_hint=True),
    )
    def batch_update(
        form_id: FormId,
        requests: Annotated[
            list[dict[str, Any]],
            Field(description="Request オブジェクトの配列。先頭から順に適用される。形式はツール説明の例を参照", min_length=1),
        ],
        include_form_in_response: Annotated[
            bool, Field(description="True なら更新後のフォーム全体をレスポンスに含める")
        ] = True,
        required_revision_id: Annotated[
            str | None, Field(description="writeControl.requiredRevisionId。現在のリビジョンと一致しないと失敗する")
        ] = None,
        target_revision_id: Annotated[
            str | None, Field(description="writeControl.targetRevisionId。このリビジョン以降の変更と協調的にマージする")
        ] = None,
    ) -> dict[str, Any]:
        if required_revision_id and target_revision_id:
            raise ToolError("required_revision_id と target_revision_id は同時に指定できません。どちらか一方にしてください。")
        body: dict[str, Any] = {"requests": requests, "includeFormInResponse": include_form_in_response}
        if required_revision_id:
            body["writeControl"] = {"requiredRevisionId": required_revision_id}
        elif target_revision_id:
            body["writeControl"] = {"targetRevisionId": target_revision_id}
        forms = get_service(services.forms)
        return execute(forms.forms().batchUpdate(formId=form_id, body=body), "forms.batchUpdate")

    @mcp.tool(annotations=ToolAnnotations(title="公開設定を変更", read_only_hint=False, idempotent_hint=True))
    def set_publish_settings(
        form_id: FormId,
        is_published: Annotated[bool, Field(description="フォームを公開するか（False にすると回答者はフォームを開けない）")],
        is_accepting_responses: Annotated[
            bool, Field(description="回答を受け付けるか。is_published=False の場合は常に False として扱われる")
        ],
    ) -> dict[str, Any]:
        """フォームの公開状態と回答受付を変更する（forms.setPublishSettings）。

        よく使う組み合わせ:
        - 公開して回答受付: is_published=True, is_accepting_responses=True
        - 公開したまま回答締め切り: is_published=True, is_accepting_responses=False
        - 非公開に戻す: is_published=False, is_accepting_responses=False

        注意: 公開設定の機能が導入される前に作られた古いフォーム（get_form の結果に publishSettings がないもの）では失敗することがある。
        戻り値: 更新後の publishSettings を含む API レスポンス。
        """
        body = {
            "publishSettings": {
                "publishState": {"isPublished": is_published, "isAcceptingResponses": is_accepting_responses}
            },
            "updateMask": "publishState",
        }
        forms = get_service(services.forms)
        return execute(forms.forms().setPublishSettings(formId=form_id, body=body), "forms.setPublishSettings")
