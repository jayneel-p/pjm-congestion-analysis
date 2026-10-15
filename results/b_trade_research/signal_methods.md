# Test B's proposed entry rules before changing the slides

Specified 9 October 2026 before calculating these new rule comparisons. The user
requests tests of the B alternatives, followed by simple trading signals in the
existing LaTeX slides if the tests support them. No new measurements are acquired.
Read the existing B methods, decision methods and uncertainty memory first.

## Physical questions and available inputs

The rival explanations are local load geography, local transfer/relieving supply
availability, and solar's effect on commitment or forecast revisions. The present
database has no within-Dominion bus load, relevant local historical outages,
signed sensitivities or local commitment, and no renewable forecasts covering
the assessment price period. Do not manufacture those tests from actual output.
An increase in Dominion's forecast share of RTO demand is a different, coarser
regional demand predictor. It cannot establish within-Dominion misallocation.

Use the canonical paired prices at DOM_RESID_AGG and DOMINION HUB. The fixed
candidate calendar is nonholiday weekdays with hour starts 10 through 15 EPT,
January–August of each year. Keep every scheduled hour, including hours without
a bid or a price-only fill. The existing cap is +5 dollars/MWh. No tuning of the
cap, lag, hurdle, hour window or direction is permitted after viewing scores.

## Rules to compare

1. **Cap only:** offer each candidate hour with maximum DA sink-minus-source
   premium +5. This repeats the existing frozen illustration.
2. **Past prices plus cap:** offer only if the mean complete six-hour daily
   RT-minus-DA basis in D−35 < date <= D−7 exceeds +1 dollars/MWh, with at least
   ten earlier days. Then apply the same +5 cap.
3. **Forecast share rises plus cap:** offer only when the six-hour mean DOM
   demand forecast divided by the corresponding RTO mean rises between the
   latest evaluations available by D−2 09:00 EPT and D−1 09:00 EPT. Require
   DOM and RTO at both cutoffs for all six hours. Apply the same +5 cap.

The third rule's zero-change threshold is a new exploratory physical-direction
choice, not a fitted cutoff or a direct geographic-load test. An evaluation time
before cutoff does not prove that the information was publicly available then.
The price delay also assumes seven-day availability of retrospectively retrieved
prices. All three rules are research reconstructions, not certified live tests.

## Accounting and evaluation

**Support-only addendum, before viewing new economic scores:** an independent
raw-table inventory finds no complete D−2 forecast for these next-day delivery
hours. Keep rule 3 as untestable, with zero offers. Add a fourth rule using
latest evaluations by D−1 06:00 and D−1 10:00 EPT. Offer if the DOM/RTO six-hour
forecast share rises between those cutoffs, with full six-hour DOM/RTO support
at both. The zero-change threshold, direction and +5 cap stay fixed. The 10:00
cutoff precedes the verified 11:00 auction deadline, although evaluation time
still does not authenticate publication. This support-driven addition does not
use price outcomes to change the rule. It remains a regional forecast-revision
predictor, not a test of internal load misallocation.

One MW is an accounting unit. A price-only fill occurs if an offered hour's DA
local-minus-hub total spread is at most +5. Profit per filled MWh is RT basis
minus DA basis minus invented remaining costs of 0, 1 or 3 dollars/MWh. Profit
is zero for no bid, missing-signal or unfilled hours. The cap limits DA price,
not RT reversal loss. Full clearing, no impact and current endpoints applied to
historical prices remain assumptions; invoices and historical eligibility are
not reconstructed.

Evaluate 2025 and January–August 2026 separately, and January–April versus
May–August within each year. Show 2024 cap-only as context. These years were
already explored; none is a fresh holdout. Give candidate/offered/filled counts,
net per filled and per candidate MWh, positive filled fraction, worst filled
hour, worst daily P&L for the 1 MW unit, maximum cumulative drawdown, and means
after removing the most profitable calendar week. Keep losing tails.

For each rule, year and cost, jointly resample complete Monday–Sunday calendar
weeks 1,999 times with fixed seed 20261009; use 14- and 28-day calendar-block
sensitivities anchored to Monday 2024-01-01. Recompute net sum divided by
candidate-hour count, retaining zero-position days and related hours together.
Also compare rules on paired calendar blocks. These historical mean ranges do
not cover search, publication, execution or future-regime uncertainty and are
not prospective profit odds.

## Research promotion rule

Before inspecting results, require all of the following for a signal to become
a supported candidate entry on the slides: at least 50 price-only filled hours
in each 2025/2026 January–August window; positive mean after invented cost 3 in
both years and both four-month subperiods; lower ends above zero at invented
cost 1 for the 7-, 14- and 28-day resampling ranges in both years; and positive
cost-1 mean after removing each year's best week. These are conservative
research triage criteria, not a claim that cost 3 is the actual fee or a universal
trading standard. Passing would justify a later untouched paper test only.
Unavailable physical inputs mean the corresponding mechanism is untested.

Retain failed rules. If none passes, the slides should say no validated B entry,
show the tested price signal and rejection reason, and keep physical inputs as
unvalidated research needs. Include clear A/C forecast-price versus quote rules
without upgrading their prior forecast or contract limitations.

## Verification and deliverables

Save hourly signal provenance, daily accounting, annual/subperiod scores,
cluster ranges, paired comparisons and explicit promotion checks under
`tables/signal_*.csv` and `signal_result.json`. Save two explanatory graphs.
An independent agent reconstructs rule inputs/accounting from SQL; uncertainty
is separately checked with a different implementation or labeled outside audit.
Preserve all fourteen LaTeX frames and the 26 existing chart panels. Put any
compact result in the existing final trading frame, with detailed source notes.
Compile with the native LaTeX compiler, inspect changed slide layout, update
evidence/progress/source uses, run both learning numeric audits and the full
assessment audit before the knowledge checker.
