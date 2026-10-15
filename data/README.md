# Canonical measurements and offline rebuild inputs

Canonical measurements are stored in `data/pjm.sqlite`. Offline rebuild inputs
include private originals in `data/raw/`, preserved cleaned public-price and
forecast snapshots in `data/processed/`, and the EPA candidate-unit snapshot
`data/raw/epa_baltimore_units_2024_2026q2.json.gz`. Keep these inputs for an
offline rebuild. The current presentation is published under `presentation/`. Its local
revision work stays under `results/trade_deck_15/` and does not change canonical measurements.

Database snapshots and original supplied measurements are retained privately. They are not public downloads. A full offline rebuild requires those retained inputs; the published slides, aggregate results and MCP/RAG code can be reviewed without them.

Start with `pjm.sqlite`, then read the [analysis methods](../scripts/analyze_flowgates.md). The canonical database contains the nine original measurement tables below and five public-history tables described at the end plus input/source provenance. New results belong under `results/base_case/`, not in the source folders.

A recorded hour is one anonymous-flowgate/hour row in the supplied constraint export. It is not necessarily a distinct binding event, a full hour of binding or an overload. The user confirms complete binding-hour coverage: no row means nonbinding during that eligible hour. The fraction counts hours containing binding, not minutes bound. Signed shadows stay missing on those hours.

## Tables, keys and units

| Table | One row | Unique key | Values |
| --- | --- | --- | --- |
| `constraints` | Recorded gate/hour | `timestamp_source, flowgate` | Supplied signed `avg_shadow_price`; whole-hour averaging user-confirmed; units provisional |
| `load` | Geography/type/hour | `timestamp_source, region_zone, load_type` | `load_value`, MW |
| `solar` | Region/hour | `timestamp_source, area` | `solar_value`, MW |
| `wind` | Region/hour | `timestamp_source, area` | `wind_value`, MW |
| `fuel_generation` | Fuel/hour | `timestamp_source, fuel_type` | `mw`, MW; supplied fuel shares retained |
| `lmps` | Supplied RT pricing location/hour | `timestamp_source, pnode_id` | Total, energy, congestion and loss components, $/MWh |
| `hourly_analysis` | Gate/source-clock hour | `timestamp, flowgate` | Record status, shadows, calendar, candidate local and PJM fundamentals, RT spreads |
| `pjm_settled_hourly_lmps` | Four-node paired DA/verified RT hour | `timestamp_utc, pnode_id` | Eight price components, source row, UTC/Eastern labels, retrieval date |
| `pjm_multi_node_hourly_lmps` | Seventeen-node paired DA/RT hour | `timestamp_utc, pnode_id` | Eight price components, metadata, current/version flags and raw-row provenance |

`data_catalog` records each input file's SHA-256, count, key and source IDs. `source_references` records descriptions, summaries, uses and verified Zotero keys. Public prices are the preserved October 7, 2026 retrieval, not an archive of predecision publication vintages.

The source-aligned panel has 70,119 rows (23,373 naive hour labels per gate) and all 10,732 constraint records. Analysis excludes five entire clock-change dates, leaving 23,256 eligible labels per gate: 4,691 A, 1,234 B and 4,765 C records. The complete public-price sources instead retain 23,375 physical UTC hours per node, including repeated autumn hours. Never replace their UTC key with an ambiguous Eastern label.

## Join safely

Join hour **and entity**. Joining every load zone or pricing node on time alone multiplies rows. Load geography overlaps: do not sum the RTO, regional and zonal values together. Regional renewables and zonal load are different footprints, so their subtraction is not measured local net load. Fuel output is system-wide.

The panel maps A to BC Zone/MIDATL/BGE_RESID_AGG, B to DOM Zone/SOUTH/DOM_RESID_AGG, and C to COMED Zone/WEST/COMED_RESID_AGG. These are candidate proxies, not identified endpoints. `lmp_spread` means local aggregate total RT LMP minus WESTERN HUB total RT LMP; `congestion_spread` uses congestion components in the same order. Positive means local is more expensive. It does not identify physical line-flow direction.

For a different load geography, filter that entity before joining:

```sql
SELECT a.timestamp, a.flowgate, a.event_recorded, l.load_value
FROM hourly_analysis AS a
LEFT JOIN load AS l
  ON a.timestamp=l.timestamp_source
 AND l.region_zone='PJM RTO Total'
 AND l.load_type='REGION'
WHERE a.flowgate='Flowgate C' AND a.dst_transition_date=0;
```

`PJM RTO Total` uses the supplied `REGION` load type; zonal labels use `ZONE`. These distinctions are retained. Price-only comparisons use UTC/node. Joining anonymous constraint records to public prices uses the provisional common source/Eastern label only after clock-date exclusions.

## Offline reproduction

```sh
uv run python scripts/clean_data.py
uv run python scripts/build_hourly_panel.py
uv run python scripts/build_database.py --output data/pjm.sqlite
```

The explicit output above rebuilds the canonical `data/pjm.sqlite` only after temporary-build checks pass. Without `--output`, the builder creates a separate `results/base_case/rebuilt.sqlite`. The builder verifies exact input readback, keys, price components and clock labels, and writes `rebuild_checks.json` and `input_catalog.csv`. Add `--compare-with data/pjm.sqlite` to reconcile every retained field and missing mask against the preserved database. See [builder methods](../scripts/build_database.md). The new panel omits unused retrospective weather fields but preserves the source measurement fields exactly.

`raw/` preserves private assessment originals, price downloads/archives and the selected case/PJM source documents. `processed/` preserves cleaned source snapshots. The six-file cleaner does not rebuild the two public-price snapshots; their original downloads, UTC keys, raw row references and retrieval vintage remain available for later source verification. The excluded generator inventory is a capacity snapshot, not historical local-unit dispatch.

Missing fundamentals remain NULL, and negative prices/readings and tails remain intact. Complete binding-hour coverage and whole-hour shadow averaging are user-confirmed. Constraint market/clock, units and exact aggregation implementation remain unresolved; [the definitions note](../docs/data_clarifications.md) states the outstanding provider questions.

## Added EPA candidate-unit snapshot

`data/raw/epa_baltimore_units_2024_2026q2.json.gz` retains the complete 131,328-row EPA CAMPD response for Brandon Shores (602) and Herbert A Wagner (1554), January 2024–June 2026, including all nonoperating hours. [Acquisition manifest](../results/base_case/local_supply_acquisition.json) records the exact facility/date query, retrieval date and both hashes. It is outside the nine-table canonical measurement database. A normal analyzer run now needs this preserved snapshot; `--local-supply-only` rebuilds only the new rival test.

EPA reports facility local standard time and gross MW during operation. Maryland is fixed UTC−5; the diagnostic converts to prevailing Eastern labels and tests ±1-hour shifts. Multiply gross MW by operating time to obtain MWh. Only explicitly nonoperating rows contribute zero; Wagner unit 2's operating electrical output remains unknown. The electrical subtotal is labeled units 1/3/4. Gross output is not net injection, available capacity, an outage classification or a verified electrical effect on anonymous A. Sources EPA01–EPA03 define acquisition and interpretation.

## Expanded public histories — 9 October 2026

The database now contains fourteen measurement tables. The builder imports the
preserved processed histories when present. Read [acquisition design/status](../results/final_review/forecasts/acquire_three_inputs.md)
and [current analysis methods](../results/new_data_review/methods.md) for exact
coverage, selection rules and source boundaries.

| Table | Rows | Unique physical/vintage key | Use |
| --- | ---: | --- | --- |
| `pjm_load_forecast_history` | 698,335 | Evaluation UTC, delivery UTC, area | RTO/MIDATL/DOM/COMED archived revisions; January 2024–August 2026 |
| `pjm_da_constraint_marginal_values` | 207,503 | Facility, contingency, hour UTC | Public hourly DA constraint context |
| `pjm_rt_constraint_marginal_values` | 595,469 | Facility, contingency, interval-start UTC | Five-minute public RT context and duration |
| `pjm_wind_forecast_history` | 177,733 | Evaluation UTC, delivery UTC | Recent September–October 2026 revisions |
| `pjm_solar_forecast_history` | 33,696 | Evaluation UTC, delivery UTC | Recent September–October 2026 revisions |

Retain every source field and revision; UTC keys govern physical hours. At the
fixed prior-day 09:00 Eastern cutoff, 118 delivery hours per load area have no
eligible snapshot, versus eight absent at every vintage. An earlier evaluation
timestamp does not prove earlier public availability. Recent renewable forecasts
have no assessment-period overlap. Public DA/RT names need source validation;
absence of an exact DA label does not establish unexpected RT binding. Public
constraint durations cannot be assigned to anonymous A/B/C.

The earlier 180-row portal sample remains acquisition history. It is superseded
by the full preserved load history, not combined as duplicate measurements.
Sources A32–A36/P24 retain verified stored Zotero keys. Existing nine-table
measurements are unchanged; the EPA unit snapshot remains outside SQLite.
