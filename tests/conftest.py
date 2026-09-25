from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import httplib2
import pytest
from googleapiclient.errors import HttpError
from mcp import Client

from forms_mcp.server import create_mcp_server

TEST_SECRET = "s" * 40


# async テストは anyio の pytest プラグイン（pytest.mark.anyio）で実行する。
# fixture とテストが同じタスクで動くため、MCP クライアントの cancel scope を安全に閉じられる。
@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeServices:
    """forms() / drive() が同じ MagicMock を返す GoogleServices。

    MagicMock はメソッドチェーン（forms().batchUpdate(...).execute()）の呼び出し引数を記録するので、
    `services.forms_api.forms.return_value.batchUpdate.assert_called_once_with(...)` のように検証できる。
    """

    def __init__(self) -> None:
        self.forms_api = MagicMock(name="forms_v1")
        self.drive_api = MagicMock(name="drive_v3")

    def forms(self) -> Any:
        return self.forms_api

    def drive(self) -> Any:
        return self.drive_api


@pytest.fixture
def services() -> FakeServices:
    return FakeServices()


@pytest.fixture
def mcp_server(services: FakeServices):
    return create_mcp_server(services, pubsub_topic=None)


@pytest.fixture
async def client(mcp_server):
    async with Client(mcp_server) as c:
        yield c


def make_http_error(status: int, message: str, google_status: str = "") -> HttpError:
    resp = httplib2.Response({"status": str(status)})
    resp.reason = "error"
    content = json.dumps({"error": {"code": status, "message": message, "status": google_status}}).encode()
    return HttpError(resp, content, uri="https://forms.googleapis.com/v1/forms/x")


def structured(result) -> dict[str, Any]:
    """CallToolResult から dict を取り出す。"""
    assert not result.is_error, result.content[0].text
    if result.structured_content is not None:
        return result.structured_content
    return json.loads(result.content[0].text)
