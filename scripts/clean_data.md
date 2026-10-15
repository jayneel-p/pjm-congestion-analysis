# Clean the six supplied time series

Cleaning fixes text representation and validates keys without changing measured values. Inputs are D01–D06's six source CSVs under `data/raw/`; outputs retain the same filenames under `data/processed/`. Original files remain unchanged. The generator inventory and weather tables are preserved source material but are outside this analysis and cleaning path.

Run:

```sh
uv run python scripts/clean_data.py
```

To verify against existing processed files without replacing them, use `--output-dir /private/tmp/pjm-clean-check`. The six-file dictionary is shared with `audit_data.py`.

The cleaner reads numeric values with round-trip float parsing, preserves pricing-node IDs as text, strips outer whitespace, converts empty text to missing values and parses source dates/timestamps. For solar/wind it checks supplied timestamp equals source date plus source hour. It verifies nonmissing unique source keys, sorts stably by them, and writes ordinary CSVs. It does not shift hours, assign a timezone, interpolate, clip extremes, normalize generation shares or fill missing fields.

The expected row counts and grains are in [the processed-data note](../data/processed/README.md). Load/generation units are MW and LMP components are $/MWh; whole-hour shadow averaging is user-confirmed, while units and exact aggregation implementation remain provisional. A missing measurement and an absent constraint record are different things. Cleaned tables are not yet an aligned panel.

The October 8 check rebuilt all six files into a temporary directory and compared every cell and missing-value position against the preserved processed inputs. `results/base_case/cleaning_checks.json` records row counts and hashes. This checks representation, not provider definitions or causality.
