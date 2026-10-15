# Rebuild the minimal source database offline

The new starting base needs source measurements and paired DA/RT prices, not 27 older analytical tables. This builder imports exactly six cleaned assessment time series, the source-aligned hourly panel and two preserved cleaned price snapshots. It does not fetch data or depend on archived plots/models/report folders.

Inputs are `data/processed/`'s six assessment CSVs, `pjm_settled_hourly_lmps.csv`, `pjm_multi_node_hourly_lmps.csv`, `results/base_case/hourly_panel.csv`, `references/analysis_sources.json` and the verified `references/zotero_items.json`. Source IDs are D01–D06 and A28/A29/A32. Original price downloads and row/vintage metadata remain preserved; the cleaner does not regenerate these two public-price snapshots.

Run from the root:

```sh
uv run python scripts/clean_data.py
uv run python scripts/build_hourly_panel.py
uv run python scripts/build_database.py --output data/pjm.sqlite
```

The default builds `results/base_case/rebuilt.sqlite` with full input readback checks. The command above replaces the canonical database only after full checks. Add `--compare-with` to reconcile against a preserved database before replacement. `--output` selects a destination and optional `--compare-with` selects a preserved database for exact reconciliation. Without the flag, an offline rebuild does not require an old database. An explicitly selected canonical destination is replaced only after the temporary build passes all checks. The active canonical database has already been replaced by the exact verified minimal build; the former full database remains in the repository snapshot.

The source tables are `constraints`, `load`, `solar`, `wind`, `fuel_generation`, `lmps`, `hourly_analysis`, `pjm_settled_hourly_lmps` and `pjm_multi_node_hourly_lmps`. `data_catalog` records source paths, hashes, counts, keys and reference IDs; `source_references` retains the annotations and verified Zotero keys. Read [the schema guide](../data/README.md) before joins.

The builder preserves source values, missing cells and original date/hour labels. It adds `timestamp_source` with the established 0-hour or minus-one-hour normalization. Missing absent-hour shadows remain SQL NULL. Unique indexes enforce the appropriate hour/entity keys; entity/time and Eastern/node indexes support correct joins. The panel excludes unused retrospective weather columns while retaining every shared original measurement exactly.

For every imported table, it reads the full SQLite table back and checks every value and missing mask against its input. When `--compare-with` is supplied it also compares all relevant fields and counts against that database. It checks SQLite integrity, reconciles all 10,732 original shadow records, verifies 70,119 panel rows and 23,256 eligible labels per gate, and checks that absent hours have no fabricated shadow values.

Price sources preserve physical UTC/node keys and both repeated autumn hours. UTC-to-America/New_York labels must agree; every node must have the complete 23,375-hour physical grid. DA and RT component totals are checked with the original feed-specific rounding tolerances: below 0.000003 $/MWh for settled four-node prices and below 0.020001 for independently rounded multi-node prices. Price values are not corrected to force these identities.

Outputs are `rebuilt.sqlite`, `input_catalog.csv` and `rebuild_checks.json` under `results/base_case/`. They document input provenance and exact reconciliation, not causal identification or information available before a historical trade. The constraint market/clock/shadow averaging and record completeness remain provisional. Retrospectively retrieved DA/RT prices do not provide issued forecast or price-quote vintages.

## Historical load forecast sample — 9 October 2026

The builder additionally imports `data/raw/forecast_final/rto_2024-01-01_portal.csv` when present into `pjm_load_forecast_history`. Its unique key is `evaluated_at_utc, forecast_hour_beginning_utc, forecast_area`. All six source fields and all 180 revisions are retained; UTC-to-Eastern conversions and exact SQLite readback are checked. The sample covers RTO and 24 delivery UTC hours on 1 January 2024 only. It does not establish historical publication before entry or forecast skill. The source-labelled Eastern timestamps have no UTC offset; use UTC for physical-hour keys.

The authenticated portal response was exported through compact exact-key/value records. Eastern labels were reconstructed from UTC and checked against a checksum of all six original browser fields (FNV-1a 3369218135), preserving every source value. The CSV is a verified measurement export, not the original JSON response envelope. A33/P24 identify the feed and access mechanics. `data_catalog` records its SHA-256 and `source_references` the verified source keys. The earlier failed acquisition record remains historical evidence.

An offline rebuild includes this tenth measurement table. Comparison against the older canonical database permits only this new table to be absent; all nine prior measurement tables must match exactly.

The requested bulk acquisition route is documented in [three-input acquisition methods](../results/final_review/forecasts/acquire_three_inputs.md). When present, processed CSVs under `data/processed/pjm_three_inputs` supply the full load-vintage table and separate DA/RT constraint and wind/solar forecast tables. Otherwise the existing load sample remains the fallback. These optional tables are never merged into actual operating measurements.

## Current expanded-history coverage — 9 October 2026

The optional public-history import is now populated, giving fourteen measurement
tables. The load/DA/RT/wind/solar counts are 698,335/207,503/595,469/177,733/33,696.
The original nine measurement tables remain separate and unchanged. Retain the
five processed CSVs and raw page/metadata snapshots for an offline rebuild. The
load archive covers RTO/MIDATL/DOM/COMED during the assessment; wind and solar
forecasts are recent September–October 2026 histories. They cannot validate a
historical renewable signal. The old portal sample is fallback history, not
the current load coverage. No builder calculations changed in this analysis.
