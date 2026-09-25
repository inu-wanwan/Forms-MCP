from __future__ import annotations

import pytest

from tests.conftest import make_http_error, structured

pytestmark = pytest.mark.anyio


async def test_get_response(client, services):
    api = services.forms_api.forms.return_value.responses.return_value
    api.get.return_value.execute.return_value = {"responseId": "R1", "answers": {"q1": {"questionId": "q1"}}}

    data = structured(await client.call_tool("get_response", {"form_id": "F1", "response_id": "R1"}))

    api.get.assert_called_once_with(formId="F1", responseId="R1")
    assert data["responseId"] == "R1"


async def test_list_responses_minimal(client, services):
    api = services.forms_api.forms.return_value.responses.return_value
    api.list.return_value.execute.return_value = {"responses": [{"responseId": "R1"}]}

    data = structured(await client.call_tool("list_responses", {"form_id": "F1"}))

    api.list.assert_called_once_with(formId="F1")
    assert data["responses"][0]["responseId"] == "R1"


async def test_list_responses_with_filter_and_paging(client, services):
    api = services.forms_api.forms.return_value.responses.return_value
    api.list.return_value.execute.return_value = {"responses": [], "nextPageToken": "next"}

    await client.call_tool(
        "list_responses",
        {"form_id": "F1", "filter": "timestamp > 2025-01-01T00:00:00Z", "page_size": 50, "page_token": "tok"},
    )

    api.list.assert_called_once_with(
        formId="F1", filter="timestamp > 2025-01-01T00:00:00Z", pageSize=50, pageToken="tok"
    )


async def test_list_responses_rejects_page_size_over_limit(client, services):
    result = await client.call_tool("list_responses", {"form_id": "F1", "page_size": 5001})
    assert result.is_error
    services.forms_api.forms.return_value.responses.return_value.list.assert_not_called()


async def test_list_responses_scope_error(client, services):
    api = services.forms_api.forms.return_value.responses.return_value
    api.list.return_value.execute.side_effect = make_http_error(
        403, "Request had insufficient authentication scopes.", "PERMISSION_DENIED"
    )

    result = await client.call_tool("list_responses", {"form_id": "F1"})

    assert result.is_error
    text = result.content[0].text
    assert "HTTP 403" in text
    assert "スコープ" in text
    assert "get_refresh_token.py" in text
