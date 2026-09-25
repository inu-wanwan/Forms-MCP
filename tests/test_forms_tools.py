from __future__ import annotations

import pytest

from tests.conftest import make_http_error, structured

pytestmark = pytest.mark.anyio


async def test_create_form(client, services):
    api = services.forms_api.forms.return_value
    api.create.return_value.execute.return_value = {
        "formId": "F1",
        "responderUri": "https://docs.google.com/forms/d/e/xyz/viewform",
        "revisionId": "r1",
        "info": {"title": "アンケート"},
    }

    data = structured(await client.call_tool("create_form", {"title": "アンケート", "document_title": "survey-2025"}))

    api.create.assert_called_once_with(
        body={"info": {"title": "アンケート", "documentTitle": "survey-2025"}}, unpublished=False
    )
    assert data["form_id"] == "F1"
    assert data["edit_url"] == "https://docs.google.com/forms/d/F1/edit"
    assert data["responder_uri"] == "https://docs.google.com/forms/d/e/xyz/viewform"
    assert data["revision_id"] == "r1"
    assert data["form"]["info"]["title"] == "アンケート"


async def test_create_form_unpublished_without_document_title(client, services):
    api = services.forms_api.forms.return_value
    api.create.return_value.execute.return_value = {"formId": "F2"}

    await client.call_tool("create_form", {"title": "T", "unpublished": True})

    api.create.assert_called_once_with(body={"info": {"title": "T"}}, unpublished=True)


async def test_get_form_returns_full_response(client, services):
    form = {
        "formId": "F1",
        "revisionId": "r9",
        "items": [
            {"itemId": "i1", "title": "Q1", "questionItem": {"question": {"questionId": "q1", "textQuestion": {}}}},
            {"itemId": "i2", "title": "Q2", "questionItem": {"question": {"questionId": "q2", "textQuestion": {}}}},
        ],
    }
    api = services.forms_api.forms.return_value
    api.get.return_value.execute.return_value = form

    data = structured(await client.call_tool("get_form", {"form_id": "F1"}))

    api.get.assert_called_once_with(formId="F1")
    assert data == form


async def test_batch_update_passes_requests_through(client, services):
    requests = [
        {"createItem": {"item": {"title": "Q"}, "location": {"index": 0}}},
        {"updateFormInfo": {"info": {"description": "d"}, "updateMask": "description"}},
    ]
    api = services.forms_api.forms.return_value
    api.batchUpdate.return_value.execute.return_value = {"replies": [{}, {}], "writeControl": {"requiredRevisionId": "r2"}}

    data = structured(await client.call_tool("batch_update", {"form_id": "F1", "requests": requests}))

    api.batchUpdate.assert_called_once_with(
        formId="F1", body={"requests": requests, "includeFormInResponse": True}
    )
    assert data["writeControl"]["requiredRevisionId"] == "r2"


async def test_batch_update_required_revision(client, services):
    api = services.forms_api.forms.return_value
    api.batchUpdate.return_value.execute.return_value = {}
    requests = [{"deleteItem": {"location": {"index": 0}}}]

    await client.call_tool(
        "batch_update",
        {"form_id": "F1", "requests": requests, "include_form_in_response": False, "required_revision_id": "r1"},
    )

    api.batchUpdate.assert_called_once_with(
        formId="F1",
        body={"requests": requests, "includeFormInResponse": False, "writeControl": {"requiredRevisionId": "r1"}},
    )


async def test_batch_update_target_revision(client, services):
    api = services.forms_api.forms.return_value
    api.batchUpdate.return_value.execute.return_value = {}
    requests = [{"deleteItem": {"location": {"index": 0}}}]

    await client.call_tool("batch_update", {"form_id": "F1", "requests": requests, "target_revision_id": "r5"})

    body = api.batchUpdate.call_args.kwargs["body"]
    assert body["writeControl"] == {"targetRevisionId": "r5"}


async def test_batch_update_rejects_both_revisions(client, services):
    result = await client.call_tool(
        "batch_update",
        {
            "form_id": "F1",
            "requests": [{"deleteItem": {"location": {"index": 0}}}],
            "required_revision_id": "a",
            "target_revision_id": "b",
        },
    )
    assert result.is_error
    assert "同時に指定できません" in result.content[0].text
    services.forms_api.forms.return_value.batchUpdate.assert_not_called()


async def test_batch_update_rejects_empty_requests(client, services):
    result = await client.call_tool("batch_update", {"form_id": "F1", "requests": []})
    assert result.is_error
    services.forms_api.forms.return_value.batchUpdate.assert_not_called()


async def test_batch_update_http_error_mentions_update_mask_and_rollback(client, services):
    api = services.forms_api.forms.return_value
    api.batchUpdate.return_value.execute.side_effect = make_http_error(
        400, "Invalid requests[0].updateItem: Update mask is required", "INVALID_ARGUMENT"
    )

    result = await client.call_tool(
        "batch_update", {"form_id": "F1", "requests": [{"updateItem": {"item": {"title": "x"}, "location": {"index": 0}}}]}
    )

    assert result.is_error
    text = result.content[0].text
    assert "HTTP 400" in text
    assert "INVALID_ARGUMENT" in text
    assert "Update mask is required" in text
    assert "updateMask" in text
    assert "ロールバック" in text


async def test_set_publish_settings(client, services):
    api = services.forms_api.forms.return_value
    api.setPublishSettings.return_value.execute.return_value = {
        "formId": "F1",
        "publishSettings": {"publishState": {"isPublished": True, "isAcceptingResponses": False}},
    }

    data = structured(
        await client.call_tool(
            "set_publish_settings", {"form_id": "F1", "is_published": True, "is_accepting_responses": False}
        )
    )

    api.setPublishSettings.assert_called_once_with(
        formId="F1",
        body={
            "publishSettings": {"publishState": {"isPublished": True, "isAcceptingResponses": False}},
            "updateMask": "publishState",
        },
    )
    assert data["publishSettings"]["publishState"]["isPublished"] is True
