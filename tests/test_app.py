from __future__ import annotations

import logging

import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from starlette.testclient import TestClient

from forms_mcp.app import build_app
from forms_mcp.auth.path_secret import SecretRedactingFilter
from forms_mcp.config import ConfigError, load_settings
from tests.conftest import TEST_SECRET, FakeServices


@pytest.fixture
def settings():
    return load_settings({"MCP_PATH_SECRET": TEST_SECRET, "RENDER_EXTERNAL_HOSTNAME": "forms-mcp.onrender.com"})


def test_healthz_and_404(settings):
    app, _ = build_app(settings, FakeServices())
    with TestClient(app, base_url="http://localhost") as http:
        assert http.get("/healthz").json() == {"status": "ok"}
        assert http.get("/").status_code == 404
        assert http.post("/mcp").status_code == 404
        assert http.post("/mcp/wrong-secret").status_code == 404
        assert http.post(f"/mcp/{TEST_SECRET}x").status_code == 404
        assert http.post(f"/mcp/{TEST_SECRET}/extra").status_code == 404


def test_unknown_host_is_rejected(settings):
    app, _ = build_app(settings, FakeServices())
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    headers = {"accept": "application/json, text/event-stream"}
    with TestClient(app, base_url="http://evil.example.com") as http:
        assert http.post(f"/mcp/{TEST_SECRET}", json=body, headers=headers).status_code == 421


@pytest.mark.anyio
@pytest.mark.parametrize("suffix", ["", "/"])
async def test_mcp_over_http_lists_tools_and_calls_get_form(settings, suffix):
    services = FakeServices()
    services.forms_api.forms.return_value.get.return_value.execute.return_value = {"formId": "F1", "items": []}
    app, mcp = build_app(settings, services)

    async with mcp.session_manager.run():
        transport = httpx2.ASGITransport(app=app)
        async with httpx2.AsyncClient(transport=transport, base_url="https://forms-mcp.onrender.com") as http:
            url = f"https://forms-mcp.onrender.com/mcp/{TEST_SECRET}{suffix}"
            async with Client(streamable_http_client(url, http_client=http)) as client:
                names = {t.name for t in (await client.list_tools()).tools}
                assert {"create_form", "get_form", "batch_update", "list_forms", "trash_form"} <= names
                result = await client.call_tool("get_form", {"form_id": "F1"})

    assert not result.is_error
    services.forms_api.forms.return_value.get.assert_called_once_with(formId="F1")


def test_config_requires_long_secret():
    with pytest.raises(ConfigError):
        load_settings({})
    with pytest.raises(ConfigError):
        load_settings({"MCP_PATH_SECRET": "short"})
    with pytest.raises(ConfigError):
        load_settings({"MCP_PATH_SECRET": "a/" * 20})


def test_config_partial_google_env_is_error():
    with pytest.raises(ConfigError, match="GOOGLE_REFRESH_TOKEN"):
        load_settings({"MCP_PATH_SECRET": TEST_SECRET, "GOOGLE_CLIENT_ID": "id", "GOOGLE_CLIENT_SECRET": "s"})


def test_config_hosts_and_secret_not_in_repr():
    s = load_settings(
        {
            "MCP_PATH_SECRET": TEST_SECRET,
            "ALLOWED_HOSTS": "a.example.com, b.example.com",
            "GOOGLE_CLIENT_ID": "id",
            "GOOGLE_CLIENT_SECRET": "client-secret-value",
            "GOOGLE_REFRESH_TOKEN": "refresh-token-value",
        }
    )
    assert "a.example.com" in s.allowed_hosts and "b.example.com" in s.allowed_hosts
    assert "https://a.example.com" in s.allowed_origins
    text = repr(s)
    for secret in (TEST_SECRET, "client-secret-value", "refresh-token-value"):
        assert secret not in text


def test_secret_redacting_filter():
    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
        ("1.2.3.4", "POST", f"/mcp/{TEST_SECRET}", "1.1", 200), None,
    )
    SecretRedactingFilter(TEST_SECRET).filter(record)
    assert TEST_SECRET not in record.getMessage()
    assert "/mcp/***" in record.getMessage()
