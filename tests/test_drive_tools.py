from __future__ import annotations

import pytest

from tests.conftest import make_http_error, structured

FIELDS = "id, name, createdTime, modifiedTime, webViewLink, trashed"

pytestmark = pytest.mark.anyio


async def test_list_forms(client, services):
    files = services.drive_api.files.return_value
    files.list.return_value.execute.return_value = {"files": [{"id": "F1", "name": "A"}]}

    data = structured(await client.call_tool("list_forms", {}))

    files.list.assert_called_once_with(
        q="mimeType='application/vnd.google-apps.form' and trashed=false",
        fields=f"nextPageToken, files({FIELDS})",
        orderBy="modifiedTime desc",
    )
    assert data["files"][0]["id"] == "F1"


async def test_list_forms_paging(client, services):
    files = services.drive_api.files.return_value
    files.list.return_value.execute.return_value = {"files": []}

    await client.call_tool("list_forms", {"page_size": 10, "page_token": "tok"})

    kwargs = files.list.call_args.kwargs
    assert kwargs["pageSize"] == 10
    assert kwargs["pageToken"] == "tok"


async def test_copy_form(client, services):
    files = services.drive_api.files.return_value
    files.copy.return_value.execute.return_value = {"id": "F2", "name": "コピー"}

    data = structured(await client.call_tool("copy_form", {"form_id": "F1", "new_title": "コピー"}))

    files.copy.assert_called_once_with(fileId="F1", body={"name": "コピー"}, fields=FIELDS)
    assert data["form_id"] == "F2"
    assert data["edit_url"] == "https://docs.google.com/forms/d/F2/edit"


async def test_trash_form(client, services):
    files = services.drive_api.files.return_value
    files.update.return_value.execute.return_value = {"id": "F1", "trashed": True}

    data = structured(await client.call_tool("trash_form", {"form_id": "F1"}))

    files.update.assert_called_once_with(fileId="F1", body={"trashed": True}, fields="id, name, trashed")
    files.delete.assert_not_called()
    assert data["trashed"] is True


async def test_copy_form_not_found_mentions_drive_file_scope(client, services):
    files = services.drive_api.files.return_value
    files.copy.return_value.execute.side_effect = make_http_error(404, "File not found: F9.", "NOT_FOUND")

    result = await client.call_tool("copy_form", {"form_id": "F9", "new_title": "x"})

    assert result.is_error
    text = result.content[0].text
    assert "HTTP 404" in text
    assert "drive.file" in text
