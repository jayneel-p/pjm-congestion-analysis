# Align the six source time series

The panel supplies one consistent hour/gate row for timing, operating-condition and price comparisons. Inputs are the six cleaned assessment CSVs in `data/processed/` (sources D01–D06). Output is `results/base_case/hourly_panel.csv`; `join_coverage.csv` records missing cells and `geographic_mapping.csv` records the candidate proxies.

```sh
uv run python scripts/build_hourly_panel.py
```

Date plus source hour defines a naive clock label for constraints, solar, wind and fuel output. Load hour and price hour-ending labels are reduced by one: date D/hour ending 24 becomes D/23:00. This retains the established alignment. Direct public-price comparisons support Eastern price labels; independent anonymous-constraint clock/market authentication is still missing.

The calendar is the shared 23,373 solar/wind/LMP source labels from January 2024 through August 2026. No spring-gap or repeated autumn label is invented. Three rows per clock label produce 70,119 gate/hour rows and retain every one of the 10,732 source constraint records. `event_recorded` means exactly that a source row exists. The user confirms complete binding coverage, so other eligible hours are nonbinding. Their shadow values remain missing.

All five US Eastern clock-change dates are flagged and remain in the panel: March 10 and November 3, 2024; March 9 and November 2, 2025; March 8, 2026. Analysis excludes those dates, leaving 23,256 eligible labels per gate. Signed shadow values and their magnitudes stay missing on absent-record hours; they are never filled with zero.

| Gate | Candidate load | Renewable region | Local price |
| --- | --- | --- | --- |
| A | BC Zone | MIDATL | BGE_RESID_AGG |
| B | DOM Zone | SOUTH | DOM_RESID_AGG |
| C | COMED Zone | WEST | COMED_RESID_AGG |

These are proxies, not known endpoints. Regional renewable output and zonal load do not have matching footprints; their subtraction is not measured local net load. Fuel output is PJM-wide historical generation, not a nearby unit's output. The August 2026 inventory is not historical dispatch.

`lmp_spread` is local aggregate total RT LMP minus WESTERN HUB total RT LMP. `congestion_spread` subtracts congestion components in the same order. Both are $/MWh. Positive means the local price is higher. It does not by itself reveal anonymous line-flow direction. Load/generation fields are MW; whole-hour shadow averaging is user-confirmed; units and exact aggregation implementation remain unresolved.

Pivot operations reject duplicate source keys. Calendar agreement, event coverage and final gate/hour uniqueness are asserted. Missing fundamentals stay missing. The minimal [database rebuild](build_database.md) compares every shared panel field, record value and missing mask against the preserved database.
