# Audit the six supplied time series

The audit establishes source keys, coverage, missingness, negative readings and price-component arithmetic before cleaning. It reads the six assessment time series under `data/raw/`; it does not read the generator inventory or unused weather/public-feed tables. Source records are D01–D06 in [the register](../docs/references.md).

Run from the repository root:

```sh
uv run python scripts/audit_data.py
```

`--data-dir` and `--output` allow an alternate restored input directory or audit destination. Default output is `results/base_case/data_audit.json`.

The JSON contains row counts, field names, proposed keys, duplicate/null counts, date/hour coverage, geography/fuel categories, shadow-price signs, negative solar readings and the maximum total-LMP minus energy/congestion/loss residual. The audit changes no files in `data/`. It does not turn absent constraint rows into nonbinding labels, identify physical paths or reject economically meaningful spikes.

Load and generation are interpreted as MW; LMP components are $/MWh. Whole-hour shadow averaging is user-confirmed. Supplied shadow units, exact aggregation implementation and the anonymous constraint market remain provisional. Raw-file keys and counts are checked again during [cleaning](clean_data.md), [hour alignment](build_hourly_panel.md) and [database rebuild](build_database.md).
