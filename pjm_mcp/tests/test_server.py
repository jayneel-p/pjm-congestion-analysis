import json
import sys
from pathlib import Path

import httpx
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from pjm_mcp.client import PJMClient, Settings
from pjm_mcp.server import create_server

EXPECTED_TOOLS = {"list_feeds", "get_feed_metadata", "query_feed"}


async def test_mcp_tool_contract_and_api_roundtrip():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"items": [{"mw": -5, "missing": None}], "totalRows": 1})

    api = PJMClient(Settings(api_key="fixture-key"), transport=httpx.MockTransport(handler))
    async with Client(create_server(api)) as client:
        tools = (await client.list_tools()).tools
        assert {tool.name for tool in tools} == EXPECTED_TOOLS
        assert all(tool.annotations.read_only_hint is True for tool in tools)
        query = next(tool for tool in tools if tool.name == "query_feed")
        assert query.input_schema["properties"]["row_count"]["maximum"] == 1000
        result = await client.call_tool("query_feed", {"feed": "gen_by_fuel"})
        assert not result.is_error
        assert result.structured_content["items"] == [{"mw": -5, "missing": None}]
        assert len(requests) == 1 and requests[0].url.host == "api.pjm.com"
    assert api.http.is_closed


async def test_mcp_missing_key_and_validation_are_errors():
    api = PJMClient(Settings())
    async with Client(create_server(api)) as client:
        catalog = await client.call_tool("list_feeds", {"search": "wind"})
        assert not catalog.is_error
        assert catalog.structured_content["count"] == 2
        error = await client.call_tool("get_feed_metadata", {"feed": "pnode"})
        assert error.is_error
        assert "PJM_API_KEY" in error.content[0].text
        error = await client.call_tool("query_feed", {"feed": "pnode", "row_count": 1001})
        assert error.is_error


async def test_real_stdio_startup_discovery_and_tool_call():
    # Real child process and MCP wire; no API key or internet request.
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "pjm_mcp.server"],
        cwd=Path(__file__).resolve().parents[1],
        env={"PJM_API_KEY": "", "PJM_REQUESTS_PER_MINUTE": "6"},
    )
    async with Client(params, read_timeout_seconds=15) as client:
        tools = await client.list_tools()
        assert {tool.name for tool in tools.tools} == EXPECTED_TOOLS
        result = await client.call_tool("list_feeds", {"search": "constraints"})
        assert not result.is_error
        assert result.structured_content["count"] == 4
        assert "pjm.sqlite" not in json.dumps(result.structured_content)
        missing = await client.call_tool("get_feed_metadata", {"feed": "pnode"})
        assert missing.is_error and "PJM_API_KEY" in missing.content[0].text
