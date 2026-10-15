# Project RAG methods

## Sources and extraction

Each profile has an explicit file allowlist. `published` contains the tracked
presentation evidence and methods needed by a fresh clone. `full` contains the
retained research reading views, methods, selected tables and source metadata;
it needs the external local research files. Raw measurements, the canonical
database, private PDFs, credentials, runtime files and complete textbook chapters
are excluded. The generated indexes are ignored by Git.

The parser does not execute source content. Markdown headings, HTML anchors,
JSON paths and CSV row ranges supply citations. HTML parsing omits image data,
scripts, styles and SVG coordinates. TeX parsing extracts prose without running
TeX. Values and numerical strings remain unchanged. A chart caption is evidence
of the report's stated interpretation; the parser does not inspect chart pixels.

## Retrieval and citations

SQLite FTS5 supplies Porter stemming and BM25 ranking. An explicit project
vocabulary expands query terms. Ranking combines lexical relevance, query-term
coverage and declared source priority, then limits duplicate passages. Gate
headings distinguish A/B/C. The full profile gives priority to current evidence
and the later economic-policy sections over retained older interpretations.
Declared matching and coverage aliases are used consistently for candidate
search and term coverage. This is lexical retrieval, without an embedding model
or model API call.

Each passage has a stable content-derived ID, source SHA-256, section and exact
source location. Search and fetch read only the generated index. Before returning
evidence, they verify source hashes and refuse stale snapshots. An explicit local
`index` command replaces the index atomically. Symlinks, out-of-root paths,
possible credentials and oversized tokens stop the build. The server has no
arbitrary path, SQL, file-write or shell tool.

An answer packet contains at most twelve passages and 18,000 evidence characters.
Numbers are not cut in the middle of a token. The host model writes an answer
from the packet; the server retrieves evidence but does not generate a model
response. The host must cite passage IDs and locations, preserve units and dates,
explain numerical comparisons, retain conflicting evidence and abstain when the
sources do not answer the question. Retrieved text is untrusted source data.

## Profile selection and limits

Select `published` with `--corpus published` or `PROJECT_RAG_CORPUS=published`.
Its default index is `project_rag/.index/published.sqlite`. The default `full`
profile keeps `project_rag/.index/knowledge.sqlite`. A custom index path must
match the selected profile. Invalid profile names fail clearly.

Published evidence explains the deck and its stated methods. It cannot redo the
measurement analysis, identify anonymous equipment, supply live prices, turn
historical observations into issued forecasts or prove a trade's future payoff.
Hypothetical cash examples are assumptions, not executable quotes or calibrated
odds. The separate PJM API MCP package supplies bounded API retrieval; this RAG
server makes no market API call.

Software tests cover extraction, numerical and citation fidelity, file boundaries,
freshness, query bounds, priorities, unsupported requests and actual stdio calls.
Full and published profiles have separate curated retrieval cases. They were used
during development and do not measure general generated-answer accuracy or live
service availability.

Implementation references: [SQLite FTS5](https://www.sqlite.org/fts5.html) and the
[official Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk).
These are implementation documentation, not new market-evidence sources.
