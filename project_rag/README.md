# PJM Project Knowledge RAG

Local evidence retrieval for questions about this project's A/B/C findings,
definitions, methods, uncertainty, presentation and trade assumptions. The MCP
host model writes the answer from cited passages. The server queries its local
index and makes no API calls.

A portable [client configuration example](client.example.json) is included.

## Use the files in a fresh clone

The `published` profile indexes visible slide text, checked presentation results,
definitions and selected methods. It needs no private files, database, authoring
snapshots or API key. It can explain what the published deck says; it cannot redo the underlying analysis or
supply live prices.

Install with Python 3.12 and uv, then run from the repository root:

```sh
uv sync --frozen --project project_rag
uv run --no-sync --project project_rag project-rag index --root . --corpus published
uv run --no-sync --project project_rag project-rag search "What does a recorded hour mean?" --root . --corpus published
uv run --no-sync --project project_rag project-rag context "What limits gate B's solar/load comparison?" --root . --corpus published
uv run --no-sync --project project_rag project-rag evaluate --root . --corpus published
```

The explicit [published allowlist](src/project_rag/corpus_published.json) contains
12 text files. Its index is `project_rag/.index/published.sqlite`, kept out of Git.
The [published client example](client.published.example.json) starts the same
three read-only MCP tools against that profile. It passes `--corpus published`
to `serve`; `PROJECT_RAG_CORPUS=published` is an equivalent process setting.

## Use the full local research

The default `full` profile preserves the existing 52-file allowlist and
`project_rag/.index/knowledge.sqlite` path. Supply those retained local files or
the separate exported knowledge bundle before indexing. The privately retained measurement database
is not the text corpus. Existing commands and installed full-workspace
MCP settings keep their default behavior:

```sh
uv run --no-sync --project project_rag project-rag index --root .
uv run --no-sync --project project_rag project-rag evaluate --root .
```

Use `--corpus full` when a process already has a different profile in its
environment. Each profile has its own default index and regression cases.
An explicit `--index` or `PROJECT_RAG_INDEX` still overrides the path; the
configuration check refuses a profile that does not match the chosen index.

For an MCP client, launch the absolute path to `project_rag/.venv/bin/project-rag`
with argument `serve`. Set `PROJECT_RAG_ROOT` to the absolute repository path.
The default private index is `project_rag/.index/knowledge.sqlite` under that
root. `PROJECT_RAG_INDEX` can point to another owner-configured index.

The three read tools search evidence, fetch a cited passage and prepare a bounded
answer packet for the host model. They cannot read an arbitrary file or query
the measurement database. Search refuses a stale index; rerun `index` after
changing an included source. `context` returns evidence and answer instructions,
not a fabricated model response. Use it with an MCP host for generated Q&A.

The [full corpus list](src/project_rag/corpus.json) controls its included files. Raw data,
private PDFs, keys, source images, prior report copies and complete textbooks are
excluded. The index itself contains private project text and stays out of Git.
HTML extraction ignores embedded image bytes, scripts and styles. Citations give
the source file, section and line, row or JSON location; HTML anchors open the
relevant report section in a local desktop client.

The [methods](methods.md) explain retrieval, freshness and verification limits.
This is local BM25 retrieval with project vocabulary expansion, without an
embedding download or an embedding API bill. It preserves the distinction
between recorded occurrence, shadow magnitude, price exposure and trade payoff.

```sh
uv run --directory project_rag --no-sync pytest
uv run --directory project_rag --no-sync ruff check .
uv run --directory project_rag --no-sync ruff format --check .
uv run --no-sync --project project_rag project-rag evaluate --root . --corpus published
uv run --no-sync --project project_rag project-rag evaluate --root .
```

Full evaluation needs the external full corpus. Published evaluation works from
the clone alone. Both are known retrieval regressions, not general answer accuracy.
