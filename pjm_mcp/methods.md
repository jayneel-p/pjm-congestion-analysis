# PJM API MCP: implementation and verification

13 October 2026. The user narrowed the request to an MCP server that talks only
to the PJM API. This package has no database, report, filesystem-read, order or
other service tools. It is separate from the seven analysis scripts and their
environment. No market measurements, forecasts, calculations or reports changed.

The official Python MCP SDK supplies stdio framing, discovery, validation,
structured results, tool errors and shutdown. Three tools expose a documented
starter catalog, live metadata and generic one-page queries. The catalog contains
25 feed short names, checked against the PJM API guide's feed sections and
appendix. It is explicitly dated and incomplete. Any valid short name may be
queried, even if absent from the starter catalog.

The client uses fixed production HTTPS URLs and GET only. Strict feed-name
validation prevents path/URL injection. Requests cannot override credentials,
output format or paging through the filter map. Source filter strings pass
unchanged through HTTP query encoding. Selected fields use commas, verified
against the live API. Entity filter values can still use semicolons. The guide's
semicolon field example failed live validation. Price examples sort by EPT,
as allowed by current metadata, while retaining UTC physical keys.
The server does not convert clocks, aggregate records, select revisions or infer
publication vintages. It returns source rows plus explicit retrieval/paging
metadata. A page is limited to 1,000 records and 2 MiB of decoded response bytes.
Separate pages do not form an atomic snapshot.

The per-process limiter defaults to six requests per minute and shares cooldowns
across calls/retries. It does not coordinate other clients using the same key.
Transient HTTP statuses and timeouts get three total attempts. Long upstream
cooldowns fail promptly and remain enforced on later calls. Redirects/proxies are
disabled, HTTP response/error bodies cannot expose the configured key, and no key
is accepted in tool arguments or written to disk. All remote tools carry MCP
read-only annotations. The local catalog is marked as a closed-world tool.

Verification covers synthetic response fidelity (negative values, missing fields,
extremes, repeated EPT labels with distinct UTC), 1-based and unknown-total paging,
case-insensitive envelope names, path/parameter rejection, response byte/row caps,
HTTP status and timeout errors, retries, concurrent rate spacing, secret
redaction, settings validation, MCP schemas/structured results and lifecycle
cleanup. A real child process completes MCP discovery and tool calls over stdio.
The package lock records the exact SDK/client/test dependencies. Lint and format
checks apply to the new package. The initial unauthenticated metadata probe
returned HTTP 401. The corrected release then passes 47 authenticated checks:
25 metadata feeds, nine data routes, UTC/entity filters, 24-hour paging and direct
API equality, plus empty/error handling. The installed wheel also works with
current and legacy SDK MCP clients. No full-history acquisition, production
client registration, electrical inference or trade validation is claimed.

## GBE acceptance and handoff extension

The [live test plan](live_test_plan.md) specifies a reproducible stdio acceptance
run, with metadata, small data pages, UTC/entity filters, paging reconstruction
and a separate direct-PJM comparison. A clean temporary environment installs the
built wheel away from the analysis repository and completes MCP discovery,
catalog lookup and the missing-key error path. The expanded 70-test fixture suite
also checks that the acceptance runner does not count auth failures as expected
query errors, cannot mistake an unexpected empty page for success, and does not
save measurements or keys in its report.

The GBE archive contains only an explicit allowlist of source, tests, lockfile,
docs, examples, wheel and sanitized verification results. Keys, environments,
caches, the analysis database and source measurements are excluded. A per-file
checksum manifest and archive SHA-256 identify the delivered bytes. The handoff
guide separates the tested macOS/Python 3.12 installation from GBE's own client,
network and account acceptance. The initial authenticated run found invalid
semicolon field encoding and unsupported UTC price sorting. Release 0.1.1 uses
comma-separated fields and valid EPT price sorting while preserving UTC keys.
It exposes bounded, redacted PJM validation messages. The dated acceptance result
records the corrected full rerun; the first failed run is preserved locally.

## Sources and review scope

### Private MCP transport and acceptance scope

This stdio server can run locally or through an owner-managed private transport.
The launching environment supplies credentials. Keep keys, tunnel profiles,
OS credential-store helpers and transport logs outside the repository. A private
transport does not add a market-data source or change the fixed PJM upstream.
Its host must remain online, and the operator must manage restart and key expiry.

The local 14 October acceptance check discovered the three read tools, made
three calls and reconciled 18 displayed values with a separate PJM response.
That small installed-client check does not certify another account, network or
GBE deployment. Private conversation URLs, screenshots and connection settings
are not part of this source publication.

PJM source P24,
[Data Miner API Guide](https://www.pjm.com/-/media/DotCom/etools/data-miner-2/data-miner-2-api-guide.pdf),
supplies subscription-header authentication, production base URL, short names,
metadata/search endpoints, fields, sort, filter and paging syntax. Targeted sections
III and VI–VIII were reviewed; this is not a complete guide audit. Its existing
Zotero key `C4F8TH6T` matches the preserved project map. No new Zotero write or
live Zotero verification occurred. The
[PJM Data Miner page](https://www.pjm.com/markets-and-operations/etools/data-miner-2)
supplies current published connection limits. Live acceptance reads small API
samples in memory; no source measurements are exported or added to the canonical
database.

The [official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk),
[running guide](https://py.sdk.modelcontextprotocol.io/run/),
[structured-output guide](https://py.sdk.modelcontextprotocol.io/servers/structured-output/)
and [error guide](https://py.sdk.modelcontextprotocol.io/servers/handling-errors/)
supplied protocol and implementation details. The
[OpenAI MCP configuration guide](https://developers.openai.com/codex/mcp)
supplied the stdio configuration and environment-forwarding fields. These are
implementation references, not new assessment evidence. They are recorded as
unsaved implementation documentation in P24's MCP-use note; no Zotero keys are
invented for them. Installed package signatures and the actual stdio test verify
the implementation independently of examples in web documentation.
