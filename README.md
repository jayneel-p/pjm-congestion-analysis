# PJM congestion analysis

Analysis of three anonymous PJM flowgates near Baltimore, Richmond and Chicago, with a current presentation and two read-only MCP servers.

## Presentation and results

Open the [37-slide PowerPoint](presentation/PJM_GBE_Assessment.pptx) or [PDF](presentation/PJM_GBE_Assessment.pdf). The slides cover cleaning, load, solar, wind, generation, prices, weather and conditional A/B/C trades. The [displayed results](results/presentation/slide_text.md), [numeric summary](results/presentation/results_summary.json) and [sources](presentation/sources.md) support the presentation. [Editing and build instructions](presentation/README.md) are included.

Price estimates are dated 14 October 2026. Forecasts were saved 15 October for 16 October delivery. The complete snapshot arrived after B's auction. The cases require current exact prices, executable quotes and available quantity before entry. Anonymous equipment and signed line flows remain unknown.

## MCP tools

[PJM API MCP](pjm_mcp/README.md) retrieves bounded feed metadata and data pages directly from PJM Data Miner. It uses PJM_API_KEY from the launching environment. Source, configuration examples, tests and a lockfile are in pjm_mcp/.

[Project Knowledge RAG](project_rag/README.md) retrieves cited passages from the presentation results and processing methods. The published profile works from a fresh clone with no private input or API key:

```sh
uv sync --frozen --project project_rag
uv run --no-sync --project project_rag project-rag index --root . --corpus published
uv run --no-sync --project project_rag project-rag evaluate --root . --corpus published
```

Use the [published MCP client example](project_rag/client.published.example.json) to connect it. Full mode uses a separate external research corpus and index. The servers return data/evidence; the host model writes the answer.

## Analysis code

Read each same-stem method note before running a script. Cleaning preserves measured values, signs, extremes and gaps. Only load and supplied price hour-ending labels shift down one hour; fuel does not. Shadow values, price differences and contractual payment remain separate. The [data guide](data/README.md) describes schemas and retained inputs; [definitions](docs/data_clarifications.md) explain the source boundaries.

The source pipeline is in scripts/. Supporting forecast, generation, matching, price and risk code is in results/new_data_review/, results/b_trade_research/ and results/trade_thesis_review/. Install the locked Python 3.12 environment with uv sync --frozen. A full rebuild requires original measurements and retained source snapshots outside Git. The exported PowerPoint remains editable without this runtime.

Source measurements and database snapshots are retained privately and are not included in the public repository. The text RAG corpus is separate from the measurement database.

Git tracks code with required setup/methods, the current presentation and its aggregate results. Private inputs, databases, full research reports/corpus, runtime dependencies and credentials remain outside the current tree.
