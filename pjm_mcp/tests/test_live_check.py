import json
from datetime import date
from types import SimpleNamespace

from pjm_mcp.client import Settings
from pjm_mcp.live_check import AcceptanceRun, price_arguments


class FakeMCP:
    def __init__(self, *, error=False, data=None, text=""):
        self.response = SimpleNamespace(
            is_error=error,
            structured_content=data,
            content=[SimpleNamespace(text=text)],
        )

    async def call_tool(self, tool, args):
        return self.response


async def test_live_runner_missing_key_is_blocked_before_network():
    run = AcceptanceRun(Settings())
    report = await run.execute(date(2026, 10, 6), full=True)
    assert report["status"] == "blocked_missing_key"
    assert report["checks"] == []
    assert report["authenticated_live_verified"] is False


async def test_expected_error_does_not_accept_an_auth_failure():
    run = AcceptanceRun(Settings(api_key="fixture-key"))
    client = FakeMCP(error=True, text="PJM authentication failed")
    await run.call(client, "unknown_feed", "get_feed_metadata", {}, expect_error="feed not found")
    assert run.checks[-1]["status"] == "failed"
    run.last_remote_finished = 0
    client = FakeMCP(error=True, text="PJM feed not found")
    await run.call(client, "unknown_feed", "get_feed_metadata", {}, expect_error="feed not found")
    assert run.checks[-1]["status"] == "passed"


async def test_unexpected_empty_page_is_not_a_live_success():
    run = AcceptanceRun(Settings(api_key="fixture-key"))
    client = FakeMCP(data={"items": [], "returned_rows": 0, "total_rows": 0})
    assert await run.call(client, "data", "query_feed", {}) is None
    assert run.checks[-1]["status"] == "failed"
    run.last_remote_finished = 0
    assert await run.call(client, "empty", "query_feed", {}, allow_empty=True) is not None


async def test_live_report_does_not_store_source_measurements_or_key():
    run = AcceptanceRun(Settings(api_key="fixture-key"))
    client = FakeMCP(
        data={
            "items": [{"total_lmp_da": 1234.56789}],
            "returned_rows": 1,
            "total_rows": 1,
        }
    )
    await run.call(client, "data", "query_feed", {})
    report = json.dumps(run.report("passed", date(2026, 10, 6), False))
    assert "1234.56789" not in report
    assert "fixture-key" not in report
    assert "total_lmp_da" in report


def test_acceptance_queries_are_fixed_and_bounded():
    args = price_arguments(date(2026, 10, 6), row_count=12, start_row=13)
    assert args["filters"] == {
        "datetime_beginning_utc": "2026-10-06 00:00 to 2026-10-06 23:59",
        "pnode_id": "51288",
    }
    assert args["row_count"] == 12 and args["start_row"] == 13
    assert args["sort"] == "datetime_beginning_ept"
