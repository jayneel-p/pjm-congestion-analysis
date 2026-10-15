"""Small, reproducible live acceptance checks through a real MCP subprocess."""

import argparse
import asyncio
import json
import statistics
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from pjm_mcp.catalog import FEEDS
from pjm_mcp.client import API_BASE, Settings, api_value

CORE_FEEDS = (
    "pnode",
    "da_hrl_lmps",
    "rt_hrl_lmps",
    "gen_by_fuel",
    "load_frcstd_hist",
    "hourly_wind_power_forecast",
    "hourly_solar_power_forecast",
    "rt_marginal_value",
)


def price_arguments(day: date, *, row_count: int = 24, start_row: int = 1) -> dict:
    return {
        "feed": "da_hrl_lmps",
        "filters": {
            "datetime_beginning_utc": f"{day} 00:00 to {day} 23:59",
            "pnode_id": "51288",
        },
        "fields": [
            "datetime_beginning_utc",
            "datetime_beginning_ept",
            "pnode_id",
            "pnode_name",
            "total_lmp_da",
            "congestion_price_da",
        ],
        "sort": "datetime_beginning_ept",
        "row_count": row_count,
        "start_row": start_row,
    }


class AcceptanceRun:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.checks: list[dict] = []
        self.last_remote_finished = 0.0
        self.interval = 60.0 / settings.requests_per_minute + 0.2

    async def spacing(self) -> None:
        delay = self.last_remote_finished + self.interval - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)

    def record(self, name: str, passed: bool, **details: Any) -> None:
        self.checks.append({"name": name, "status": "passed" if passed else "failed", **details})
        print(f"{'PASS' if passed else 'FAIL'} {name}", flush=True)

    async def call(
        self,
        client: Client,
        name: str,
        tool: str,
        args: dict,
        *,
        expect_error: str | None = None,
        allow_empty: bool = False,
    ) -> dict | None:
        remote = tool != "list_feeds"
        if remote:
            await self.spacing()
        started = time.perf_counter()
        try:
            response = await client.call_tool(tool, args)
        except Exception as error:
            self.record(name, False, error_type=type(error).__name__)
            return None
        finally:
            if remote:
                self.last_remote_finished = time.monotonic()
        elapsed = round(time.perf_counter() - started, 3)
        if expect_error:
            message = " ".join(getattr(block, "text", "") for block in response.content)
            self.record(
                name,
                response.is_error and expect_error in message,
                duration_seconds=elapsed,
            )
            return None
        if response.is_error:
            message = " ".join(getattr(block, "text", "") for block in response.content)
            # ToolError messages come from this server's sanitized client, not upstream bodies.
            if self.settings.api_key:
                message = message.replace(self.settings.api_key, "[REDACTED]")
            self.record(name, False, duration_seconds=elapsed, error=message[:400])
            return None
        data = response.structured_content
        if not isinstance(data, dict):
            self.record(
                name, False, duration_seconds=elapsed, error="Missing structured MCP result."
            )
            return None
        details: dict[str, Any] = {"duration_seconds": elapsed}
        passed = True
        if tool == "query_feed":
            items = data.get("items")
            passed = isinstance(items, list) and (bool(items) or allow_empty)
            details.update(
                returned_rows=data.get("returned_rows"), total_rows=data.get("total_rows")
            )
            if isinstance(items, list):
                details["response_field_names"] = sorted({field for row in items for field in row})
            passed = passed and not data.get("pagination_warning")
        elif tool == "get_feed_metadata":
            passed = isinstance(data.get("data"), dict) and bool(data["data"])
        self.record(name, passed, **details)
        return data if passed else None

    async def execute(self, day: date, full: bool) -> dict:
        if not self.settings.api_key:
            return self.report("blocked_missing_key", day, full)
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "pjm_mcp.server"],
            env={
                "PJM_API_KEY": self.settings.api_key,
                "PJM_REQUESTS_PER_MINUTE": str(self.settings.requests_per_minute),
            },
        )
        async with Client(params, read_timeout_seconds=180) as client:
            started = time.perf_counter()
            tools = (await client.list_tools()).tools
            self.record(
                "stdio_tool_discovery",
                {tool.name for tool in tools} == {"list_feeds", "get_feed_metadata", "query_feed"},
                duration_seconds=round(time.perf_counter() - started, 3),
            )
            await self.call(client, "catalog_search", "list_feeds", {"search": "load"})
            feeds = tuple(feed[0] for feed in FEEDS) if full else CORE_FEEDS
            for index, feed in enumerate(feeds):
                result = await self.call(
                    client,
                    f"metadata:{feed}",
                    "get_feed_metadata",
                    {"feed": feed},
                )
                if index == 0 and result is None:
                    # One auth/connectivity failure is enough; do not repeat it 25 times.
                    return self.report("failed_preflight", day, full)

            day_filter = {"datetime_beginning_utc": f"{day} 00:00 to {day} 23:59"}
            cases = [
                ("da_prices_fixed_day", price_arguments(day)),
                (
                    "rt_prices_fixed_day",
                    {
                        "feed": "rt_hrl_lmps",
                        "filters": {**day_filter, "pnode_id": "51288"},
                        "sort": "datetime_beginning_ept",
                        "row_count": 5,
                    },
                ),
                (
                    "preliminary_load",
                    {"feed": "hrl_load_prelim", "filters": day_filter, "row_count": 5},
                ),
                ("fuel_generation", {"feed": "gen_by_fuel", "filters": day_filter, "row_count": 5}),
                (
                    "historical_load_forecasts",
                    {
                        "feed": "load_frcstd_hist",
                        "row_count": 5,
                        "filters": {
                            "forecast_hour_beginning_utc": f"{day} 00:00 to {day} 23:59",
                            "forecast_area": "RTO",
                        },
                    },
                ),
                ("wind_forecast_vintages", {"feed": "hourly_wind_power_forecast", "row_count": 5}),
                (
                    "solar_forecast_vintages",
                    {"feed": "hourly_solar_power_forecast", "row_count": 5},
                ),
                (
                    "da_constraints",
                    {"feed": "da_marginal_value", "filters": day_filter, "row_count": 5},
                ),
                (
                    "rt_constraints",
                    {"feed": "rt_marginal_value", "filters": day_filter, "row_count": 5},
                ),
            ]
            fixed_prices = None
            for name, args in cases:
                result = await self.call(client, name, "query_feed", args)
                if name == "da_prices_fixed_day":
                    fixed_prices = result

            if fixed_prices is not None:
                expected = fixed_prices["items"]
                self.record(
                    "da_complete_utc_day",
                    len(expected) == 24,
                    returned_rows=len(expected),
                    expected_rows=24,
                )
                timestamps = [str(row.get("datetime_beginning_utc", "")) for row in expected]
                self.record(
                    "utc_and_entity_filters",
                    len(set(timestamps)) == 24
                    and all(stamp.startswith(str(day)) for stamp in timestamps)
                    and all(str(row.get("pnode_id")) == "51288" for row in expected),
                )
                first = await self.call(
                    client, "page_one", "query_feed", price_arguments(day, row_count=12)
                )
                second = await self.call(
                    client,
                    "page_two",
                    "query_feed",
                    price_arguments(day, row_count=12, start_row=13),
                )
                if first is not None and second is not None:
                    combined = first["items"] + second["items"]
                    self.record("paging_equals_single_page", combined == expected)
                    self.record(
                        "continuation_metadata",
                        first["next_start_row"] == 13
                        and second["next_start_row"] is None
                        and first["has_more"] is True
                        and second["has_more"] is False,
                    )
                await self.spacing()
                started = time.perf_counter()
                args = price_arguments(day)
                direct_params = {
                    **args["filters"],
                    "fields": ",".join(args["fields"]),
                    "sort": args["sort"],
                    "order": "Asc",
                    "rowCount": 24,
                    "startRow": 1,
                    "format": "json",
                }
                try:
                    async with httpx.AsyncClient(
                        timeout=30,
                        follow_redirects=False,
                        trust_env=False,
                    ) as raw:
                        response = await raw.get(
                            API_BASE + args["feed"],
                            params=direct_params,
                            headers={"Ocp-Apim-Subscription-Key": self.settings.api_key},
                        )
                    raw_items = (
                        api_value(response.json(), "items") if response.status_code == 200 else None
                    )
                    self.record(
                        "direct_api_equals_mcp",
                        raw_items == expected,
                        http_status=response.status_code,
                        duration_seconds=round(time.perf_counter() - started, 3),
                        rows_compared=len(expected),
                    )
                except (httpx.RequestError, ValueError, AttributeError) as error:
                    self.record("direct_api_equals_mcp", False, error_type=type(error).__name__)
                finally:
                    self.last_remote_finished = time.monotonic()

            empty = await self.call(
                client,
                "empty_query_is_success",
                "query_feed",
                {
                    "feed": "da_hrl_lmps",
                    "filters": {**day_filter, "pnode_id": "999999999999999"},
                    "row_count": 1,
                },
                allow_empty=True,
            )
            if empty is not None:
                self.record("empty_query_contains_zero_rows", empty["returned_rows"] == 0)
            await self.call(
                client,
                "unknown_feed_is_error",
                "get_feed_metadata",
                {"feed": "nonexistent_pjm_mcp_acceptance_feed"},
                expect_error="PJM feed not found",
            )
            await self.call(
                client,
                "invalid_field_is_error",
                "query_feed",
                {
                    "feed": "da_hrl_lmps",
                    "fields": ["nonexistent_acceptance_field"],
                    "filters": {**day_filter, "pnode_id": "51288"},
                    "row_count": 1,
                },
                expect_error="PJM rejected the query",
            )
        return self.report(
            "passed" if all(row["status"] == "passed" for row in self.checks) else "failed",
            day,
            full,
        )

    def report(self, status: str, day: date, full: bool) -> dict:
        durations = [row["duration_seconds"] for row in self.checks if "duration_seconds" in row]
        return {
            "status": status,
            "tested_at_utc": datetime.now(UTC).isoformat(),
            "query_date_utc": day.isoformat(),
            "full_catalog_metadata": full,
            "authenticated_live_verified": status == "passed",
            "passed": sum(row["status"] == "passed" for row in self.checks),
            "failed": sum(row["status"] == "failed" for row in self.checks),
            "timing_scope": "One run; latency excludes pacing. No uptime/load SLA.",
            "median_call_seconds": statistics.median(durations) if durations else None,
            "max_call_seconds": max(durations) if durations else None,
            "checks": self.checks,
            "limits": [
                "This account and test time only; GBE must verify its own key and entitlement.",
                "No live outage/rate-limit induction, orders, settlement or forecasting test.",
                "No source measurements, account identity or API keys included in this report.",
            ],
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--full", action="store_true", help="Check metadata for all 25 catalog feeds."
    )
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        default=datetime.now(UTC).date() - timedelta(days=7),
    )
    parser.add_argument("--output", type=Path, default=Path("live_results.json"))
    args = parser.parse_args()
    settings = Settings.from_env()
    run = AcceptanceRun(settings)
    try:
        report = asyncio.run(run.execute(args.date, args.full))
    except Exception as error:
        run.record("test_runner_failure", False, error_type=type(error).__name__)
        report = run.report("failed", args.date, args.full)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        f"Live acceptance: {report['status']}; "
        f"{report['passed']} passed, {report['failed']} failed."
    )
    if report["status"] == "blocked_missing_key":
        print("Set PJM_API_KEY in the launching environment; no authenticated request was made.")
        raise SystemExit(2)
    raise SystemExit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
