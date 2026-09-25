from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from google.auth.exceptions import RefreshError
from mcp.server.mcpserver.exceptions import ToolError

from forms_mcp.auth import MissingCredentialsError
from forms_mcp.errors import execute, format_http_error, get_service
from tests.conftest import make_http_error


def _request(side_effect=None, result=None):
    req = MagicMock()
    req.execute.side_effect = side_effect
    req.execute.return_value = result
    return req


def test_execute_returns_result():
    assert execute(_request(result={"a": 1}), "forms.get") == {"a": 1}


def test_execute_normalizes_empty_body():
    assert execute(_request(result=""), "forms.watches.delete") == {}


@pytest.mark.parametrize(
    ("status", "message", "google_status", "expected"),
    [
        (400, "updateMask is required", "INVALID_ARGUMENT", "updateMask"),
        (400, "Index 10 out of bounds", "INVALID_ARGUMENT", "location.index"),
        (400, "Revision mismatch", "FAILED_PRECONDITION", "revisionId"),
        (400, "Invalid topic name", "INVALID_ARGUMENT", "forms-notifications@system.gserviceaccount.com"),
        (400, "Something odd", "INVALID_ARGUMENT", "camelCase"),
        (401, "Request had invalid authentication credentials.", "UNAUTHENTICATED", "リフレッシュトークン"),
        (403, "Request had insufficient authentication scopes.", "PERMISSION_DENIED", "スコープ不足"),
        (403, "The caller does not have permission", "PERMISSION_DENIED", "権限がない"),
        (403, "Google Forms API has not been used in project 1 before or it is disabled.", "PERMISSION_DENIED", "有効"),
        (404, "Requested entity was not found.", "NOT_FOUND", "drive.file"),
        (429, "Quota exceeded", "RESOURCE_EXHAUSTED", "レート制限"),
        (503, "Backend error", "UNAVAILABLE", "一時的"),
    ],
)
def test_format_http_error_hints(status, message, google_status, expected):
    text = format_http_error(make_http_error(status, message, google_status), "forms.get")
    assert f"HTTP {status}" in text
    assert google_status in text
    assert message in text
    assert "考えられる原因" in text
    assert expected in text


def test_batch_update_error_mentions_rollback():
    text = format_http_error(make_http_error(400, "bad", "INVALID_ARGUMENT"), "forms.batchUpdate")
    assert "ロールバック" in text


def test_execute_wraps_http_error_as_tool_error():
    err = make_http_error(404, "Requested entity was not found.", "NOT_FOUND")
    with pytest.raises(ToolError) as exc:
        execute(_request(side_effect=err), "forms.get")
    assert "HTTP 404" in str(exc.value)
    assert exc.value.__cause__ is err


def test_execute_wraps_refresh_error():
    with pytest.raises(ToolError) as exc:
        execute(_request(side_effect=RefreshError("invalid_grant: Token has been expired or revoked.")), "forms.get")
    text = str(exc.value)
    assert "invalid_grant" in text
    assert "get_refresh_token.py" in text


def test_execute_handles_non_json_error_body():
    import httplib2
    from googleapiclient.errors import HttpError

    resp = httplib2.Response({"status": "502"})
    resp.reason = "Bad Gateway"
    with pytest.raises(ToolError) as exc:
        execute(_request(side_effect=HttpError(resp, b"<html>bad gateway</html>")), "forms.get")
    assert "HTTP 502" in str(exc.value)


def test_get_service_missing_credentials():
    def factory():
        raise MissingCredentialsError("未設定")

    with pytest.raises(ToolError, match="未設定"):
        get_service(factory)
