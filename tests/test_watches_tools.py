from __future__ import annotations

import pytest
from mcp import Client

from forms_mcp.server import create_mcp_server
from tests.conftest import structured

pytestmark = pytest.mark.anyio

TOPIC = "projects/p/topics/forms"


async def test_create_watch_with_explicit_topic(client, services):
    api = services.forms_api.forms.return_value.watches.return_value
    api.create.return_value.execute.return_value = {"id": "w1", "state": "ACTIVE"}

    data = structured(
        await client.call_tool("create_watch", {"form_id": "F1", "event_type": "RESPONSES", "topic_name": TOPIC})
    )

    api.create.assert_called_once_with(
        formId="F1", body={"watch": {"target": {"topic": {"topicName": TOPIC}}, "eventType": "RESPONSES"}}
    )
    assert data["id"] == "w1"


async def test_create_watch_uses_default_topic_and_watch_id(services):
    api = services.forms_api.forms.return_value.watches.return_value
    api.create.return_value.execute.return_value = {"id": "my-watch"}
    mcp = create_mcp_server(services, pubsub_topic="projects/p/topics/default")

    async with Client(mcp) as client:
        await client.call_tool("create_watch", {"form_id": "F1", "event_type": "SCHEMA", "watch_id": "my-watch"})

    api.create.assert_called_once_with(
        formId="F1",
        body={
            "watch": {"target": {"topic": {"topicName": "projects/p/topics/default"}}, "eventType": "SCHEMA"},
            "watchId": "my-watch",
        },
    )


async def test_create_watch_without_topic_is_clear_error(client, services):
    result = await client.call_tool("create_watch", {"form_id": "F1", "event_type": "RESPONSES"})

    assert result.is_error
    assert "PUBSUB_TOPIC" in result.content[0].text
    services.forms_api.forms.return_value.watches.return_value.create.assert_not_called()


async def test_create_watch_rejects_unknown_event_type(client, services):
    result = await client.call_tool("create_watch", {"form_id": "F1", "event_type": "ALL", "topic_name": TOPIC})
    assert result.is_error
    services.forms_api.forms.return_value.watches.return_value.create.assert_not_called()


async def test_list_watches(client, services):
    api = services.forms_api.forms.return_value.watches.return_value
    api.list.return_value.execute.return_value = {"watches": [{"id": "w1"}]}

    data = structured(await client.call_tool("list_watches", {"form_id": "F1"}))

    api.list.assert_called_once_with(formId="F1")
    assert data["watches"][0]["id"] == "w1"


async def test_renew_watch(client, services):
    api = services.forms_api.forms.return_value.watches.return_value
    api.renew.return_value.execute.return_value = {"id": "w1", "expireTime": "2025-01-08T00:00:00Z"}

    await client.call_tool("renew_watch", {"form_id": "F1", "watch_id": "w1"})

    api.renew.assert_called_once_with(formId="F1", watchId="w1", body={})


async def test_delete_watch(client, services):
    api = services.forms_api.forms.return_value.watches.return_value
    api.delete.return_value.execute.return_value = {}

    data = structured(await client.call_tool("delete_watch", {"form_id": "F1", "watch_id": "w1"}))

    api.delete.assert_called_once_with(formId="F1", watchId="w1")
    assert data == {"deleted": True, "form_id": "F1", "watch_id": "w1"}
