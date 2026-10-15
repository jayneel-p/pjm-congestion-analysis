# Adversarial trade thesis review

Written 9 October 2026 before building the saved diagnostic tables and graphs,
after exploratory inspection of existing results. This review challenges
the current primary report, its embedded ten-slide presentation, the learning
report and the current fourteen-frame assessment source. It proposes replacement
theses without changing those deliverables, measurements, estimators or models.

The decision question is whether the proposed exposure has a demonstrated price
advantage at entry. Rival explanations are a local price response that misses the
ticket, a condition that moves both legs together, an already priced discount,
and forecast errors that change with the operating regime. Falsifiers include
failure on all covered hours, absent incremental forecast value, sign reversal
and losses on the proposed side outside the claimed predictive range.

Reuse saved, audited CSVs only. Recompute complete next-day A/C forecast errors
from `decisions/tables/selected_2026.csv`, with actual minus predicted as the
signed error. A negative error hurts a long entered near forecast value; a
positive error hurts a short. These are errors, not actual trading profits.
Report below-5th/above-95th counts, monthly equal-day prediction and realization
means, and model RMSE on identical dates. July–August is a retrospective stability
diagnostic chosen during this skeptical review. It cannot select a replacement
model, threshold, entry or calibrated future probability.

Use `trading/tables/block_hours.csv` to contrast B-selected peak hours with all
peak hours on identical Jan–Aug 2026 price support. Compute each named total RT
spread minus its named total DA spread. Separate the local ACCA/Dominion target
from Dominion/Western. Anonymous status is used only on eligible source labels;
the all-price support preserves physical UTC hours. No sum of locations, shadow
price payout or virtual-trade return is inferred.

Use `base_case/tables/c_block_monthly.csv` to show C's eight complete monthly
off-peak research means. A hypothetical short entry of -20 dollars/MWh and
remaining cost of 1 implies net arithmetic of -21 minus the monthly spread.
These entries and costs are invented. Month counts do not estimate future odds.
Research means do not certify official ICE settlement; the live COO/PJD pages
retain different averaging wording. Weight Jan–February concentration and the
remaining-month mean by the saved covered physical hours.

Each material comparison has a saved table and graph. The independent audit
uses Python standard-library CSV arithmetic, checks source score reconciliation,
reconstructs monthly/error/block comparisons without importing the analysis,
and verifies hashes and unchanged original deliverables. It does not refit trees,
rebuild the full price feed, validate publication vintages or establish an edge.

Sources reused: A29/A32 paired prices, A33 archived load, T02 documented decision
and risk scope, and I01/I02/I04/I05 product boundaries. Fresh targeted ICE page
access checks listing, market, indices, hours and monthly averaging wording only.
Existing Zotero keys are checked against the retained local map; no new save or
full source review is claimed. No new measurements or executable quotes acquired.
