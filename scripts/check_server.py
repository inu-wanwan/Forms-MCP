"""起動中のサーバーに Streamable HTTP で接続し、ツール一覧の取得と get_form の呼び出しを確認する。

使い方:
    uv run python scripts/check_server.py http://localhost:8000/mcp/<MCP_PATH_SECRET>
    uv run python scripts/check_server.py https://<app>.onrender.com/mcp/<MCP_PATH_SECRET> --form-id <formId>
"""

from __future__ import annotations

import argparse
import json

import anyio
from mcp import Client


async def run(url: str, form_id: str | None) -> int:
    async with Client(url) as client:
        tools = (await client.list_tools()).tools
        print(f"ツール数: {len(tools)}")
        for tool in tools:
            first_line = (tool.description or "").strip().splitlines()[0] if tool.description else ""
            print(f"  - {tool.name}: {first_line}")

        if not form_id:
            print("\n--form-id を指定すると get_form も呼び出します。")
            return 0

        result = await client.call_tool("get_form", {"form_id": form_id})
        text = result.content[0].text if result.content else ""
        if result.is_error:
            print(f"\nget_form がエラーを返しました:\n{text}")
            return 1
        data = result.structured_content or json.loads(text)
        info = data.get("info", {})
        print(f"\nget_form OK: title={info.get('title')!r} items={len(data.get('items', []))} revisionId={data.get('revisionId')}")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("url", help="MCP エンドポイント URL（/mcp/<MCP_PATH_SECRET> まで含める）")
    parser.add_argument("--form-id", help="get_form で取得するフォーム ID")
    args = parser.parse_args()
    return anyio.run(run, args.url, args.form_id)


if __name__ == "__main__":
    raise SystemExit(main())
