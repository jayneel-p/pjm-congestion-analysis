import asyncio
import json
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from urllib.parse import quote

import httpx
import pytest

from pjm_mcp.client import (
    API_BASE,
    MAX_RESPONSE_BYTES,
    PJMClient,
    PJMError,
    RateLimiter,
    Settings,
    retry_delay,
)

TEST_KEY = "fixture-secret-do-not-use"


class Clock:
    def __init__(self):
        self.now = 1000.0
        self.sleeps = []

    async def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds
        await asyncio.sleep(0)


@pytest.fixture
def make_client():
    clients = []

    def factory(handler, *, key=TEST_KEY):
        clock = Clock()
        limiter = RateLimiter(6, clock=lambda: clock.now, sleep=clock.sleep)
        api = PJMClient(
            Settings(api_key=key), transport=httpx.MockTransport(handler), limiter=limiter
        )
        clients.append(api)
        return api, clock

    yield factory
    assert all(client.http.is_closed for client in clients)


async def test_query_preserves_source_values_and_paging(make_client):
    requests = []
    original = [
        {
            "datetime_beginning_utc": "2026-11-01T05:00:00",
            "datetime_beginning_ept": "2026-11-01T01:00:00",
            "pnode_id": 51288,
            "total_lmp_da": -120.5,
            "missing": None,
        },
        {
            "datetime_beginning_utc": "2026-11-01T06:00:00",
            "datetime_beginning_ept": "2026-11-01T01:00:00",
            "pnode_id": 51288,
            "total_lmp_da": 1800.0,
            "missing": None,
        },
    ]

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"items": original, "totalRows": "7"})

    api, _ = make_client(handler)
    try:
        result = await api.query(
            "da_hrl_lmps",
            filters={"pnode_id": "51288;51217"},
            fields=["datetime_beginning_utc", "pnode_id", "total_lmp_da"],
            sort="datetime_beginning_ept",
            row_count=2,
            start_row=3,
        )
        request = requests[0]
        assert request.method == "GET"
        assert str(request.url).startswith(API_BASE)
        assert request.url.host == "api.pjm.com"
        assert request.headers["Ocp-Apim-Subscription-Key"] == TEST_KEY
        assert TEST_KEY not in str(request.url)
        assert dict(request.url.params) == {
            "rowCount": "2",
            "startRow": "3",
            "format": "json",
            "pnode_id": "51288;51217",
            "fields": "datetime_beginning_utc,pnode_id,total_lmp_da",
            "sort": "datetime_beginning_ept",
            "order": "Asc",
        }
        assert result["items"] == original
        assert result["total_rows"] == 7
        assert result["has_more"] is True
        assert result["next_start_row"] == 5
        assert datetime.fromisoformat(result["retrieved_at_utc"]).utcoffset() == timedelta(0)
    finally:
        await api.close()


async def test_metadata_uses_only_pjm_and_redacts_echoed_key(make_client):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "fields": [{"name": "evaluated_at_utc"}],
                "url": f"https://api.pjm.com/?subscription-key={TEST_KEY}",
                "Ocp-Apim-Subscription-Key": TEST_KEY,
            },
        )

    api, _ = make_client(handler)
    try:
        result = await api.metadata("load_frcstd_hist")
        assert requests[0].url.path == "/api/v1/load_frcstd_hist/metadata"
        assert not requests[0].url.query
        assert result["data"]["fields"] == [{"name": "evaluated_at_utc"}]
        assert TEST_KEY not in json.dumps(result)
        assert "Ocp-Apim-Subscription-Key" not in result["data"]
        assert TEST_KEY not in repr(api.settings)
    finally:
        await api.close()


@pytest.mark.parametrize(
    "feed", ["../pnode", "https://example.com", "/pnode", "pnode?x=1", "pnode%2f", "Pnode"]
)
async def test_rejects_paths_and_urls_without_request(make_client, feed):
    def fail(request):
        pytest.fail("Invalid feed should never reach HTTP")

    api, _ = make_client(fail)
    try:
        with pytest.raises(PJMError):
            await api.metadata(feed)
    finally:
        await api.close()


@pytest.mark.parametrize(
    "filters",
    [
        {"subscription-key": "other"},
        {"Ocp-Apim-Subscription-Key": "other"},
        {"Authorization": "other"},
        {"rowCount": "50000"},
        {"format": "csv"},
        {"download": "true"},
        {"start_row": "0"},
        {"pnode_id": ""},
        {"pnode_id": "x" * 2001},
        {"bad field": "1"},
    ],
)
async def test_rejects_reserved_or_invalid_filters(make_client, filters):
    api, _ = make_client(lambda request: pytest.fail("Invalid filters reached HTTP"))
    try:
        with pytest.raises(PJMError):
            await api.query("pnode", filters=filters)
    finally:
        await api.close()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"row_count": 0},
        {"row_count": 1001},
        {"start_row": 0},
        {"fields": []},
        {"fields": ["x"] * 101},
        {"sort": "../field"},
        {"order": "wrong"},
    ],
)
async def test_rejects_unbounded_or_invalid_queries(make_client, kwargs):
    api, _ = make_client(lambda request: pytest.fail("Invalid query reached HTTP"))
    try:
        with pytest.raises(PJMError):
            await api.query("pnode", **kwargs)
    finally:
        await api.close()


async def test_missing_key_never_requests(make_client):
    api, _ = make_client(lambda request: pytest.fail("Missing key reached HTTP"), key="")
    try:
        with pytest.raises(PJMError, match="PJM_API_KEY"):
            await api.metadata("pnode")
    finally:
        await api.close()


@pytest.mark.parametrize("status", [301, 302, 307, 308, 400, 401, 403, 404, 500])
async def test_errors_and_redirects_do_not_leak_or_follow(make_client, status):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            status,
            text=TEST_KEY,
            headers={"Location": "https://example.com/stolen"},
        )

    api, _ = make_client(handler)
    try:
        with pytest.raises(PJMError) as caught:
            await api.query("pnode")
        assert TEST_KEY not in str(caught.value)
        assert len(seen) == 1
        assert all(request.url.host == "api.pjm.com" for request in seen)
    finally:
        await api.close()


@pytest.mark.parametrize("status", [429, 502, 503, 504])
async def test_retries_transient_status_and_respects_cooldown(make_client, status):
    starts = []

    def handler(request):
        starts.append(clock.now)
        if len(starts) == 1:
            return httpx.Response(status, headers={"Retry-After": "20"})
        return httpx.Response(200, json={"items": [], "totalRows": 0})

    api, clock = make_client(handler)
    try:
        result = await api.query("pnode")
        assert result["has_more"] is False
        assert result["next_start_row"] is None
        assert starts[1] - starts[0] >= 20
    finally:
        await api.close()


async def test_exhausted_retries_and_long_retry_after(make_client):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "0"})

    api, _ = make_client(handler)
    try:
        with pytest.raises(PJMError, match="429"):
            await api.query("pnode")
        assert len(calls) == 3
    finally:
        await api.close()
    calls.clear()
    api, _ = make_client(
        lambda request: calls.append(request) or httpx.Response(429, headers={"Retry-After": "120"})
    )
    try:
        with pytest.raises(PJMError, match="120"):
            await api.query("pnode")
        with pytest.raises(PJMError, match="cooldown"):
            await api.query("pnode")
        assert len(calls) == 1
    finally:
        await api.close()


async def test_timeout_retry_and_network_error_redaction(make_client):
    calls = []

    def timeout(request):
        calls.append(request)
        raise httpx.ReadTimeout(TEST_KEY, request=request)

    api, _ = make_client(timeout)
    try:
        with pytest.raises(PJMError, match="three attempts") as caught:
            await api.query("pnode")
        assert len(calls) == 3
        assert TEST_KEY not in str(caught.value)
    finally:
        await api.close()

    def offline(request):
        raise httpx.ConnectError(TEST_KEY, request=request)

    api, _ = make_client(offline)
    try:
        with pytest.raises(PJMError, match="network") as caught:
            await api.query("pnode")
        assert TEST_KEY not in str(caught.value)
    finally:
        await api.close()


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"errors": [{"message": TEST_KEY}]},
        {"items": "wrong"},
        {"items": [1]},
        {"items": [], "totalRows": -1},
        {"items": [], "totalRows": True},
        {"items": [], "totalRows": "1.5"},
    ],
)
async def test_rejects_invalid_response_shapes(make_client, payload):
    api, _ = make_client(lambda request: httpx.Response(200, json=payload))
    try:
        with pytest.raises(PJMError) as caught:
            await api.query("pnode")
        assert TEST_KEY not in str(caught.value)
    finally:
        await api.close()


@pytest.mark.parametrize("body", [b"<html>no JSON</html>", b"x" * (MAX_RESPONSE_BYTES + 1)])
async def test_invalid_json_and_response_size_are_bounded(make_client, body):
    api, _ = make_client(lambda request: httpx.Response(200, content=body))
    try:
        with pytest.raises(PJMError):
            await api.query("pnode")
    finally:
        await api.close()


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"Items": [{"v": 1}], "TotalRows": "1"}, (False, None)),
        ({"items": [{"v": 1}]}, (None, 2)),
        ({"items": []}, (False, None)),
    ],
)
async def test_end_pages_and_unknown_totals(make_client, payload, expected):
    api, _ = make_client(lambda request: httpx.Response(200, json=payload))
    try:
        result = await api.query("pnode", row_count=1)
        assert (result["has_more"], result["next_start_row"]) == expected
    finally:
        await api.close()


async def test_inconsistent_source_paging_is_explicit(make_client):
    api, _ = make_client(lambda request: httpx.Response(200, json={"items": [], "totalRows": 5}))
    try:
        result = await api.query("pnode")
        assert result["pagination_warning"]
        assert result["next_start_row"] is None
    finally:
        await api.close()


async def test_response_cannot_exceed_requested_rows(make_client):
    api, _ = make_client(lambda request: httpx.Response(200, json={"items": [{"v": 1}, {"v": 2}]}))
    try:
        with pytest.raises(PJMError, match="more rows"):
            await api.query("pnode", row_count=1)
    finally:
        await api.close()


async def test_concurrent_requests_share_rate_limit(make_client):
    starts = []

    def handler(request):
        starts.append(clock.now)
        return httpx.Response(200, json={"items": [], "totalRows": 0})

    api, clock = make_client(handler)
    try:
        await asyncio.gather(*(api.query("pnode") for _ in range(8)))
        assert len(starts) == 8
        assert all(right - left >= 10 for left, right in zip(starts, starts[1:]))
    finally:
        await api.close()


def test_retry_after_http_date_and_invalid_headers():
    stamp = datetime.now(UTC) + timedelta(seconds=25)
    assert 23 <= retry_delay(format_datetime(stamp), 0) <= 25
    for value in [None, "nonsense", "NaN", "Infinity", "-1"]:
        assert retry_delay(value, 0) == 2


def test_settings_validation_and_key_redaction(monkeypatch):
    monkeypatch.setenv("PJM_API_KEY", " key ")
    monkeypatch.setenv("PJM_REQUESTS_PER_MINUTE", "6")
    assert Settings.from_env().api_key == "key"
    for value in ["no", "0", "601"]:
        monkeypatch.setenv("PJM_REQUESTS_PER_MINUTE", value)
        with pytest.raises(PJMError):
            Settings.from_env()
    monkeypatch.setenv("PJM_REQUESTS_PER_MINUTE", "6")
    monkeypatch.setenv("PJM_API_KEY", "key\nheader")
    with pytest.raises(PJMError):
        Settings.from_env()


async def test_url_encoded_key_is_redacted(make_client):
    key = "fixture+key/value"
    api, _ = make_client(
        lambda request: httpx.Response(200, json={"echo": quote(key, safe="")}), key=key
    )
    try:
        result = await api.metadata("pnode")
        assert result["data"]["echo"] == "[REDACTED]"
    finally:
        await api.close()


async def test_upstream_validation_errors_are_helpful_bounded_and_redacted(make_client):
    payload = {
        "errors": [
            {"field": "Fields", "message": "Invalid field names in the request."},
            {"field": "Sort", "message": "Sort field is not sortable."},
            {"field": "Auth", "message": TEST_KEY},
        ],
        "feedMetadata": {"private_ignored": TEST_KEY},
    }
    api, _ = make_client(lambda request: httpx.Response(400, json=payload))
    try:
        with pytest.raises(PJMError) as caught:
            await api.query("da_hrl_lmps")
        message = str(caught.value)
        assert "Fields: Invalid field names" in message
        assert "Sort: Sort field is not sortable" in message
        assert TEST_KEY not in message
        assert "feedMetadata" not in message
    finally:
        await api.close()


async def test_large_validation_body_falls_back_without_exposure(make_client):
    body = b"x" * (64 * 1024 + 1)
    api, _ = make_client(lambda request: httpx.Response(400, content=body))
    try:
        with pytest.raises(PJMError, match="get_feed_metadata"):
            await api.query("pnode")
    finally:
        await api.close()
