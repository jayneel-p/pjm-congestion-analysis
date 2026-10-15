import json
import sys

from mcp import Client
from mcp.client.stdio import StdioServerParameters

from project_rag.server import create_server

TOOLS = {"search_project", "fetch_evidence", "prepare_answer"}


async def check_contract(client):
    tools = (await client.list_tools()).tools
    assert {tool.name for tool in tools} == TOOLS
    assert all(tool.annotations.read_only_hint for tool in tools)
    assert all(not tool.annotations.open_world_hint for tool in tools)
    result = await client.call_tool("prepare_answer", {"question": "gate B solar matching"})
    assert not result.is_error
    packet = result.structured_content
    assert "504/1,139" in json.dumps(packet)
    identifier = packet["evidence"][0]["id"]
    fetched = await client.call_tool("fetch_evidence", {"passage_id": identifier})
    assert not fetched.is_error and fetched.structured_content["id"] == identifier
    search = await client.call_tool("search_project", {"query": "gate B economic policy"})
    assert not search.is_error and search.structured_content["results"]
    error = await client.call_tool("fetch_evidence", {"passage_id": "../current.md"})
    assert error.is_error
    error = await client.call_tool("search_project", {"query": "gate B", "limit": 13})
    assert error.is_error


async def test_in_memory_mcp_contract(fixture_index):
    async with Client(create_server(fixture_index)) as client:
        await check_contract(client)


async def test_real_stdio_discovery_and_all_three_tools(fixture_index):
    # Use the same production server through a real child process/MCP wire.
    code = (
        "import json,sys; from pathlib import Path; "
        "from project_rag.index import EvidenceIndex; "
        "from project_rag.server import create_server; "
        "create_server(EvidenceIndex(Path(sys.argv[1]),Path(sys.argv[2]),"
        "json.loads(sys.argv[3]))).run(transport='stdio')"
    )
    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-c",
            code,
            str(fixture_index.root),
            str(fixture_index.path),
            json.dumps(fixture_index.corpus),
        ],
    )
    async with Client(params, read_timeout_seconds=15) as client:
        await check_contract(client)
