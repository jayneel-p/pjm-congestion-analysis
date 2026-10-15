"""Bounded, read-only calls to the production PJM Data Miner API."""

import asyncio
import json
import math
import os
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Literal
from urllib.parse import quote, quote_plus

import httpx

API_BASE = "https://api.pjm.com/api/v1/"
MAX_ROWS = 1000
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_RETRY_WAIT = 30.0
NAME = re.compile(r"[a-z][a-z0-9_]{0,99}\Z")
RESERVED_FILTERS = {
    "rowcount",
    "startrow",
    "sort",
    "order",
    "fields",
    "format",
    "download",
    "subscriptionkey",
    "ocpapimsubscriptionkey",
    "apikey",
    "authorization",
}
RETRY_STATUSES = {429, 502, 503, 504}


class PJMError(Exception):
    """An error that is safe to return to the MCP client."""


@dataclass(frozen=True)
class Settings:
    api_key: str = field(default="", repr=False)
    requests_per_minute: int = 6

    def __post_init__(self) -> None:
        if not 1 <= self.requests_per_minute <= 600:
            raise PJMError("PJM_REQUESTS_PER_MINUTE must be an integer from 1 to 600.")

    @classmethod
    def from_env(cls) -> "Settings":
        try:
            rpm = int(os.environ.get("PJM_REQUESTS_PER_MINUTE", "6"))
        except ValueError:
            raise PJMError("PJM_REQUESTS_PER_MINUTE must be an integer from 1 to 600.") from None
        key = os.environ.get("PJM_API_KEY", "").strip()
        if any(ord(char) < 33 or ord(char) > 126 for char in key):
            raise PJMError("PJM_API_KEY must contain only printable ASCII without spaces.")
        return cls(api_key=key, requests_per_minute=rpm)


class RateLimiter:
    """Space starts evenly, including retries and concurrent tool calls."""

    def __init__(
        self,
        rpm: int,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.interval = 60.0 / rpm + 0.01
        self.clock = clock
        self.sleep = sleep
        self.next_start = 0.0
        self.lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self.lock:
            while self.next_start > self.clock():
                delay = self.next_start - self.clock()
                if delay > MAX_RETRY_WAIT:
                    raise PJMError(
                        f"PJM request cooldown: retry after at least {math.ceil(delay)} seconds."
                    )
                await self.sleep(delay)
            self.next_start = self.clock() + self.interval

    def defer(self, seconds: float) -> None:
        self.next_start = max(self.next_start, self.clock() + seconds)


def validate_name(value: str) -> str:
    if not NAME.fullmatch(value):
        raise PJMError("Use lowercase letters, digits and underscores for feed and field names.")
    return value


def retry_delay(value: str | None, attempt: int) -> float:
    """Honor seconds or HTTP-date Retry-After; invalid headers use bounded backoff."""
    if value:
        try:
            delay = float(value)
            if math.isfinite(delay) and delay >= 0:
                return delay
        except ValueError:
            pass
        try:
            stamp = parsedate_to_datetime(value)
            if stamp.tzinfo is not None:
                return max(0.0, (stamp - datetime.now(UTC)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            pass
    return float(2 ** (attempt + 1))


def api_value(payload: dict, key: str) -> Any:
    return next(
        (value for name, value in payload.items() if name.casefold() == key.casefold()), None
    )


class PJMClient:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        limiter: RateLimiter | None = None,
    ) -> None:
        self.settings = settings
        self.limiter = limiter or RateLimiter(settings.requests_per_minute)
        self.http = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=False,
            trust_env=False,
            transport=transport,
            limits=httpx.Limits(max_connections=4),
        )

    async def close(self) -> None:
        await self.http.aclose()

    def redact(self, value: Any) -> Any:
        """Protect the key even if upstream echoes it in a link or error."""
        if isinstance(value, str):
            key = self.settings.api_key
            if key:
                for secret in {key, quote(key, safe=""), quote_plus(key)}:
                    value = value.replace(secret, "[REDACTED]")
            return value
        if isinstance(value, list):
            return [self.redact(item) for item in value]
        if isinstance(value, dict):
            return {
                self.redact(key): self.redact(item)
                for key, item in value.items()
                if re.sub(r"[^a-z]", "", key.casefold())
                not in RESERVED_FILTERS
                - {
                    "rowcount",
                    "startrow",
                    "sort",
                    "order",
                    "fields",
                    "format",
                    "download",
                }
            }
        return value

    async def request(
        self, feed: str, *, metadata: bool = False, params: dict | None = None
    ) -> dict:
        validate_name(feed)
        if not self.settings.api_key:
            raise PJMError("Set PJM_API_KEY in the MCP server environment using your PJM API key.")
        url = API_BASE + feed + ("/metadata" if metadata else "")
        headers = {
            "Ocp-Apim-Subscription-Key": self.settings.api_key,
            "Accept": "application/json",
            "User-Agent": "pjm-api-mcp/0.1.1",
        }
        for attempt in range(3):
            await self.limiter.wait()
            try:
                async with self.http.stream("GET", url, params=params, headers=headers) as response:
                    status = response.status_code
                    if status in RETRY_STATUSES:
                        delay = retry_delay(response.headers.get("Retry-After"), attempt)
                        self.limiter.defer(delay)
                        if attempt == 2 or delay > MAX_RETRY_WAIT:
                            raise PJMError(
                                f"PJM HTTP {status}: retry after {math.ceil(delay)} seconds."
                            )
                        continue
                    errors = {
                        400: "PJM rejected the query. Check filters/fields with get_feed_metadata.",
                        401: "PJM authentication failed. Check PJM_API_KEY and API subscription.",
                        403: "PJM denied access. Check your account's permission for this feed.",
                        404: "PJM feed not found. Check its API short name.",
                    }
                    if status == 400:
                        # PJM includes useful field/sort diagnostics. Keep them bounded,
                        # redact secrets, and omit its full metadata/response body.
                        error_body = bytearray()
                        async for chunk in response.aiter_bytes():
                            error_body.extend(chunk)
                            if len(error_body) > 64 * 1024:
                                break
                        details = []
                        try:
                            error_payload = json.loads(error_body)
                            problems = api_value(error_payload, "errors")
                            if isinstance(problems, list):
                                for problem in problems[:5]:
                                    if isinstance(problem, dict):
                                        field = self.redact(str(problem.get("field", "Query")))[:80]
                                        message = self.redact(str(problem.get("message", "")))[:240]
                                        details.append(f"{field}: {message}")
                        except (ValueError, UnicodeError, AttributeError):
                            pass
                        detail = " ".join(details) or "Check filters/fields with get_feed_metadata."
                        raise PJMError("PJM rejected the query. " + detail)
                    if status in errors:
                        raise PJMError(errors[status])
                    if not 200 <= status < 300:
                        raise PJMError(f"PJM returned HTTP {status}; no data was returned.")
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_RESPONSE_BYTES:
                            raise PJMError(
                                "PJM response exceeds 2 MiB. Reduce rows, fields or date range."
                            )
                try:
                    payload = json.loads(body)
                except (ValueError, UnicodeError):
                    raise PJMError("PJM returned an invalid JSON response.") from None
                if not isinstance(payload, dict):
                    raise PJMError("Unexpected PJM response: expected a JSON object.")
                if api_value(payload, "errors"):
                    raise PJMError("PJM reported a query error. Check metadata and filters.")
                return {
                    "data": self.redact(payload),
                    "source_url": url,
                    "retrieved_at_utc": datetime.now(UTC).isoformat(),
                }
            except httpx.TimeoutException:
                if attempt == 2:
                    raise PJMError(
                        "PJM timed out after three attempts. Try a narrower query."
                    ) from None
                self.limiter.defer(retry_delay(None, attempt))
            except httpx.RequestError:
                raise PJMError(
                    "Could not reach the PJM API. Check network and TLS connectivity."
                ) from None
        raise PJMError("PJM request failed.")  # All attempts above either return or raise.

    async def metadata(self, feed: str) -> dict:
        return await self.request(feed, metadata=True)

    async def query(
        self,
        feed: str,
        *,
        filters: dict[str, str] | None = None,
        fields: list[str] | None = None,
        sort: str | None = None,
        order: Literal["Asc", "Desc"] = "Asc",
        row_count: int = 100,
        start_row: int = 1,
    ) -> dict:
        validate_name(feed)
        if not 1 <= row_count <= MAX_ROWS or start_row < 1:
            raise PJMError("row_count must be 1–1000; start_row must be at least 1 (1-based).")
        if order not in {"Asc", "Desc"}:
            raise PJMError("order must be Asc or Desc.")
        params: dict[str, str | int] = {
            "rowCount": row_count,
            "startRow": start_row,
            "format": "json",
        }
        if filters:
            if len(filters) > 30:
                raise PJMError("Use at most 30 filters per query.")
            for name, value in filters.items():
                normalized = re.sub(r"[^a-z]", "", name.casefold())
                if normalized in RESERVED_FILTERS:
                    raise PJMError(
                        "Use explicit paging/field/sort arguments. Auth overrides are forbidden."
                    )
                validate_name(name)
                if not isinstance(value, str) or not value or len(value) > 2000:
                    raise PJMError(
                        "Filter values must be nonempty strings of at most 2000 characters."
                    )
                params[name] = value
        if fields is not None:
            if not 1 <= len(fields) <= 100:
                raise PJMError(
                    "Select 1–100 field names, or omit fields to keep all source fields."
                )
            params["fields"] = ",".join(validate_name(name) for name in fields)
        if sort:
            params.update(sort=validate_name(sort), order=order)
        result = await self.request(feed, params=params)
        payload = result.pop("data")
        items = api_value(payload, "items")
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise PJMError("Unexpected PJM data page: expected an items array of records.")
        if len(items) > row_count:
            raise PJMError("PJM returned more rows than requested. Narrow the query and retry.")
        total = api_value(payload, "totalRows")
        if total is not None:
            if isinstance(total, bool) or not re.fullmatch(r"[0-9]+", str(total)):
                raise PJMError("PJM returned an invalid totalRows value.")
            total = int(total)
        next_row = start_row + len(items)
        has_more = (
            next_row <= total if total is not None else (None if len(items) == row_count else False)
        )
        paging_warning = None
        if not items and has_more:
            paging_warning = "Empty page before totalRows; refine the query rather than advancing."
        elif total is not None and items and next_row - 1 > total:
            paging_warning = "Page extends beyond totalRows; source contents may have changed."
        return {
            **result,
            "feed": feed,
            "query": self.redact(params),
            "items": items,
            "returned_rows": len(items),
            "total_rows": total,
            "has_more": has_more,
            "next_start_row": next_row if items and has_more is not False else None,
            "pagination_warning": paging_warning,
            "notes": (
                "One source page only. Pages are not a frozen snapshot. Retain UTC/entity keys, "
                "EPT labels and forecast evaluation times; retrieval time is not publication time."
            ),
        }
