# Generation trends beside each gate

Specified 9 October 2026 before calculation. The question is whether the changing
PJM generation mix changes the interpretation of A/B/C, rather than treating a
pooled binding-hour difference as a permanent relationship. A rival is that fuel
output changes throughout PJM without a stable gate-specific excess. A useful
falsifier of a universal fuel rule is a reversal in the binding-minus-comparable-
nonbinding difference. No data are acquired and no forecast or cause is fitted.

Read `fuel_generation` directly from read-only canonical SQLite. Require unique
source-hour/fuel keys and all ten measured fuels in an hour. Preserve zeros and
negative measurements. Join each gate's recorded status on the established
source labels after excluding its five documented clock-change dates. Output is
PJM-wide actual MW, not local generation, capacity, availability or net exports.
These are fuel categories; individual B/C plant histories have not been acquired.

Monthly means use every complete eligible source hour, with observed/eligible
counts. Annual comparisons use January–August in 2024/2025/2026. Standardize
all-hour annual output and average hourly shares to the same month × hour ×
weekday/weekend weights from complete 2024 observations, on cells present in all
three years. Report each year's counts; this is calendar balance, not weather
normalization. Shares divide each hour's fuel output by all ten fuels' total,
then average; never divide annual means and label that an average hourly share.

For each gate/year separately, compare recorded hours with mean nonrecorded
output in the same year/month/hour/weekday-weekend cell, requiring at least three
complete nonrecorded controls. All fuels share the same complete-hour support.
Weight retained target hours equally and preserve available/retained counts.
These conditional means use different target hours in different years; their
trend is descriptive, not a controlled causal change. No new uncertainty bars
are calculated and small point differences do not establish a reliable effect.
Existing pooled uncertainty, state-match limits and counterexamples remain.

Four vector figures show monthly PJM output and ten-fuel annual comparisons for
A/B/C. They are inline SVGs, with PNG copies for visual QA, preserving all 82
existing PNG embeds. Slide supply panels replace their pooled fuel bars with
gas/nuclear/coal binding-minus-control trends; all ten fuels and absolute levels
remain in the report and tables. Edit the authoritative assessment source in
place, preserve fourteen frames and the solar/wind panels, compile natively and
refresh the companion guide because its three fuel panels change.

A's separate nearby-plant table repeats the saved January–June physical-month
gross-output averages for Brandon Shores and Wagner units 1/3/4. It retains
unknown Wagner unit 2 and links to the earlier monthly graph. These plant data
have a different clock and period from the PJM annual comparison. Gross output
may respond to binding and cannot establish availability or signed relief.

Sources reused: D01 (`AU3FMYYS`), D05 (`ULQRPD25`), EPA01 (`JQ9QQEHS`), and
EPA02 (`HGLNW4IZ`), checked against the verified stored key map.
No new source review or Zotero save is claimed. The independent audit reconstructs
every output table from raw SQL/group loops and verifies saved plant values;
it does not establish electrical identity, causal effects or future odds.

Rebuild: `.venv/bin/python results/new_data_review/generation/analyze.py`, then
`audit.py`, the primary renderer, both existing numeric audits, the assessment
and density audits, fresh browser QA, integration seal and knowledge checker.
