# PJM API MCP

A standalone, read-only [Model Context Protocol](https://modelcontextprotocol.io/)
server for the production PJM Data Miner API. Its only remote data source is
`https://api.pjm.com/api/v1/`. It does not read the analysis database or reports.
The Python environment and lockfile are separate from the analysis pipeline.

## Install and run

Use Python 3.12 and [uv](https://docs.astral.sh/uv/). This directory is a
self-contained package. From inside it:

```sh
uv sync --frozen --no-dev
uv run --no-sync pjm-mcp
```

Set the key before using the remote tools, as described below. From the analysis
repository's root, the equivalent installation command is:

```sh
uv sync --frozen --no-dev --project pjm_mcp
```

Get a Data Miner subscription key from your profile in the
[PJM API portal](https://apiportal.pjm.com/). Set `PJM_API_KEY` in the environment
that launches the server. Keep the key in your client's secret/environment
settings. The tools never accept a key as an argument.

For a terminal session, this zsh/bash command reads the key without displaying it
or putting its value in shell history:

```sh
read -rs PJM_API_KEY
export PJM_API_KEY
```

Then start the server:

```sh
uv run --no-sync --project pjm_mcp pjm-mcp
```

It waits for an MCP client on stdin/stdout. Use `--help` or `--version` to check
the command without starting a session. At runtime, `--no-sync` prevents uv from
resolving or downloading packages.

## Connect an MCP client

The transport is **stdio**. After installation, any local MCP client can launch
the absolute path to `pjm_mcp/.venv/bin/pjm-mcp`. On Windows, use
`pjm_mcp/.venv/Scripts/pjm-mcp.exe`. Pass `PJM_API_KEY` in the server environment.

For Codex, copy [codex.example.toml](codex.example.toml) into the appropriate
MCP configuration and replace its absolute project path. It forwards
`PJM_API_KEY` from the environment of the app that launches the server. A desktop
app started from the Dock may not inherit a terminal's environment; use the
app's MCP environment settings or launch it from the configured environment.
The [official configuration guide](https://developers.openai.com/codex/mcp)
describes the supported client settings. Restart/reconnect the client after
adding the server. This repository does not change your global client settings.

For clients with a JSON `mcpServers` configuration, the equivalent is:

```json
{
  "mcpServers": {
    "pjm": {
      "command": "/ABSOLUTE/PATH/pjm_mcp/.venv/bin/pjm-mcp",
      "env": {"PJM_API_KEY": "SET_IN_YOUR_CLIENT_SECRET_SETTINGS"}
    }
  }
}
```

The value above is a placeholder. Use the client's secret settings where
available, and keep configurations containing a real key outside version control.

### ChatGPT

ChatGPT can reach this stdio server through
[OpenAI Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels).
Run the tunnel client on a host that can launch `pjm-mcp`, with `PJM_API_KEY` in
its environment. Associate the tunnel with the intended ChatGPT workspace, then
add and install a custom MCP plugin using that tunnel. The PJM server still
queries only the PJM API; OpenAI supplies the MCP transport.

The host must stay online with the tunnel running for discovery and tool calls.
Store runtime credentials in the host's secret store and keep them out of
profiles, chat and command arguments. The
[connection guide](https://developers.openai.com/plugins/deploy/connect-chatgpt)
describes current registration and acceptance steps. GBE should use its own
account, key, host and workspace permissions.

## Tools

| Tool | Result |
| --- | --- |
| `list_feeds(search="")` | Search 25 bundled starter feeds by words. This list is dated and not exhaustive; no API call or key is needed. |
| `get_feed_metadata(feed)` | Fetch PJM's current field definitions, filtering/sorting options and archive restrictions. |
| `query_feed(feed, ...)` | Fetch one page directly from any valid PJM feed short name. Supports API filter strings, field selection, sorting and 1-based paging. |

Start by inspecting metadata. For example, call `get_feed_metadata` with
`{"feed": "da_hrl_lmps"}`, then call `query_feed` with:

```json
{
  "feed": "da_hrl_lmps",
  "filters": {
    "datetime_beginning_utc": "2026-10-12 00:00 to 2026-10-12 23:59",
    "pnode_id": "51288;51217"
  },
  "fields": [
    "datetime_beginning_utc", "datetime_beginning_ept", "pnode_id",
    "pnode_name", "total_lmp_da", "congestion_price_da"
  ],
  "sort": "datetime_beginning_ept",
  "order": "Asc",
  "row_count": 100,
  "start_row": 1
}
```

This is an example request, not a saved price result. PJM decides whether a field
is filterable for the requested feed and archive period. The server forwards
filter values as written, including date ranges and semicolon-separated IDs.
PJM errors become MCP tool errors rather than successful empty results.
The client encodes selected fields with commas. These price feeds permit EPT
sorting; UTC remains the physical timestamp key in the returned rows. Use the
sorting flags in metadata for each feed rather than assuming every field is sortable.

Responses include `items`, `returned_rows`, `total_rows`, `has_more`,
`next_start_row`, the request parameters, source URL and UTC retrieval time.
Use `next_start_row` to request another page with the same filters and sort.
`has_more: null` means PJM omitted a total and the page was full, so another page
may exist. An inconsistent empty page returns a warning without advancing.

Each call returns at most 1,000 rows and 2 MiB of decoded JSON. There is no
automatic full-history download. Pages are separate live requests; they are not
a frozen snapshot. Use narrow date/entity ranges, sort, and reconcile UTC/entity
keys when combining pages. This is especially important while a rolling feed is
changing. Archived LMP queries can require different filters and separate date
ranges on each side of the archive cutoff.

## Request behavior

The default is six requests per minute per server process, spaced evenly. PJM
publishes limits of six for nonmembers and 600 for members on its
[Data Miner page](https://www.pjm.com/markets-and-operations/etools/data-miner-2).
Set `PJM_REQUESTS_PER_MINUTE` from 1 to 600 only within your account's entitlement.
Other apps and additional server processes share the account's allowance; their
usage is outside this limiter. Use one server process per key when possible.

HTTP 429/502/503/504 and timeouts get at most two retries. `Retry-After` sets a
shared cooldown. A wait longer than 30 seconds returns a retry message and keeps
the cooldown for subsequent calls. Authentication and query errors are not
retried. Network timeouts are 30 seconds, with a 10-second connection timeout.

Only GET requests to the fixed production API are permitted. Redirects and
environment proxy settings are disabled. Credentials go in the subscription
header, never in a query URL. Response/error handling redacts the configured key.
The server does not save data or credentials to disk. The bundled catalog comes
from documented short names; live metadata remains authoritative.

Keep UTC keys, EPT labels, entity IDs and forecast evaluation timestamps. An
evaluation time does not establish when a forecast became public. Retrieval time
does not turn revised history into an issued forecast. LMPs, congestion components
and constraint marginal values measure different things; the server returns
their source fields without calculating spreads, flow direction or trade value.

## Verify or develop

```sh
uv sync --frozen --project pjm_mcp
uv run --directory pjm_mcp --no-sync pytest
uv run --directory pjm_mcp --no-sync ruff check .
uv run --directory pjm_mcp --no-sync ruff format --check .
```

These commands run inside the package directory. Tests use synthetic API
responses, plus a real stdio subprocess. They do not download market data.

Checked 13 October 2026, release **0.1.1**: **70 local tests and 47 authenticated
live checks pass**. All 25 starter metadata feeds and nine data routes succeed.
Two price pages exactly reconstruct a 24-hour response, which also matches a
direct PJM API request. Live testing corrected comma-separated field encoding
and EPT price sorting. The wheel installs outside the analysis repository and
works with current and legacy SDK MCP modes. Source rows, credentials and account
identity are excluded from the handoff report. See [methods.md](methods.md) for
scope; GBE must accept its own key, client and network.

## Live acceptance

With `PJM_API_KEY` configured, run this from inside the package:

```sh
uv run --no-sync python -m pjm_mcp.live_check --full --date 2026-10-06 --output live_results.json
```

The harness starts a real MCP subprocess, checks all starter-feed metadata, reads
small samples, compares two pages with one page, and compares fixed DA records
with a direct PJM API request. It also checks empty results and upstream errors.
It uses the same conservative rate and takes several minutes. Reports exclude
source measurements and keys. See [methods.md](methods.md) for scope.
