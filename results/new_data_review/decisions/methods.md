# Forecast the price that the position receives

Specified 9 October 2026 before calculation. The user asks to finish the trading
analysis using forecasts and information a trader could have seen. Existing
actual-state results explain mechanisms; they do not choose entries here.

The decision is a research next-day block spread at prior-day 09:00 Eastern.
Targets are complete physical-hour DA total BGE_RESID_AGG-minus-WESTERN HUB peak
(A), DA total DOMINION HUB-minus-WESTERN HUB peak (B-hub), RT total ACCA-minus-
DOMINION HUB peak (B-local), and DA total COMED_RESID_AGG-minus-WESTERN HUB off-peak
(C). B-local is a diagnostic without a verified ticket; A's index differs from
BGE Zone. A next-day model does not value a month-long ICE future. For a month,
known settlement inputs and jointly forecast remaining inputs must follow each
contract’s verified averaging and MWh rules. The archive has no month-ahead fundamentals or executable quotes.

No new measurements are acquired. Use previously audited archived forecast
vintages, latest evaluation no later than the cutoff, for RTO/MIDATL/DOM/COMED.
Require all four areas for every covered physical hour; retain public UTC keys,
including clock-change dates because no anonymous-label join occurs. Average each
area over the block and retain its maximum and last-minus-first forecast change.
Overlapping footprints are separate; they are never summed or called exports.
No delivery-time actual load, renewable output, fuel dispatch, anonymous binding,
next-day DA constraint or future price is an input.

Delayed price features use only completed daily blocks dated at least seven days
before delivery. Within the same block-day class, retain the last price, 28-day
mean, 84-day mean and 84-day population standard deviation. This deliberately
assumes those retrospectively retrieved prices were available after seven days;
original publication/revision vintages are not authenticated. Forecast evaluation
before cutoff also does not authenticate public availability. These boundaries
make the work a dated information reconstruction, not a certified live backtest.

Fit fixed models on the first of each month, beginning July 2024. Use only target
blocks dated no later than seven days before that month, at most 730 calendar
days, at least 60 complete rows. Training weights have a 90-day half-life. Fixed
XGBRegressor: squared-error loss, 120 trees, depth 2, learning rate .05,
min_child_weight 10, lambda 20, no row/column subsampling, one thread, fixed seed.
No test outcomes tune parameters or select features. Features are calendar cycles,
weekday, full-day class and covered hours, plus delayed prices; the demand model
adds the four archived-load means/maxima/changes. Compare with a delayed 28-day
same-class mean. The price-history tree uses the same estimator without demand
forecasts, separating a load-information test from model complexity.

For each date and model, collect its own earlier rolling predictions' raw errors
from the preceding 180 days, dated at least seven days earlier, in the same
block-day class. Require 20 errors. Scenarios equal today's raw price prediction
plus each retained raw error; their mean is the bias-corrected point prediction.
This uses whole daily block errors, preserving intraday aggregation. It does not
preserve dependence across future days or turn daily errors into monthly paths.
Use empirical 5/50/95-percentiles, actual coverage, below/above-interval fractions,
PIT, interval width, exact empirical CRPS and probability of negative settlement.
These are empirically checked research distributions, without exchangeability or
future calibration guarantees. Retain all extremes and disclose tail sample size.

Evaluate 2025 and January–August 2026 on identical complete rows. Give MAE/RMSE,
bias, distributions, 90% coverage, CRPS, and paired squared-error/CRPS differences
against the recent-price benchmark. Resample complete Monday–Sunday weeks jointly
799 times; include 14-day sensitivity. These intervals omit specification search
and future regime changes. These periods were already explored. Select the 2026
model once using lowest 2025 squared error through December 24, before any 2026
outcome; retain all candidates and their failures. Do not select using 2026 scores.

The quote tool replays historical forecasts, never labels one as today's forecast.
For a user-supplied hypothetical quote q and cost c, long outcomes are S-q-c and
short outcomes q-S-c. Show expected outcome, empirical loss fraction, unconditional
expected loss, worst-5%-mass average profit, and a stress-size ceiling based on
entered loss budget and covered hours. Exact tail mass splits a boundary atom.
No quote is prefilled or claimed executable. Default stress is an empirical worst
scenario, not a loss bound; allow a larger entered stress. An unverified contract,
publication, weak benchmark result or failed calibration warrants passing on live
use. The tool provides arithmetic, not validated odds or an order instruction.

Rebuild: analyze.py, audit.py, then the primary renderer and current integration
checker. Five graphs show scores, complete-block paths, calibration, errors and
quote sensitivity. The presentation uses a native SVG mean-profit view with larger
labels, independently checked against the same audited scenarios. All model/training/calibration source dates and row membership
are saved. The independent audit reconstructs inputs from SQLite and saved prices,
checks predictions from saved model files, and separately reconstructs scenarios,
scores, selection and quote/tail arithmetic. It does not independently refit trees.

Sources reused: A33/P24 evaluated-vintage definitions, A32 paired prices, T02
information timing/distributions/risk, ML01 official XGBoost estimator interface
(freshly checked fixed parameters, fit/predict and threading), and I01/I04/I05
contract-location/horizon boundaries. Existing verified keys remain the citation
map; no new Zotero save is claimed. The sklearn HGB documentation was considered
as an implementation alternative but that estimator is not used.
