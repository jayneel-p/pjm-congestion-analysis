# Compact empirical flowgate analysis

## B: sunny-hour controls and a local RT signature (8 October 2026)

`--b-investigation-only` writes `results/short_case/b_investigation.json` and new
`b_*.csv` evidence, without changing canonical measurements or base results.
The question is what distinguishes B records from similar sunny operating hours,
and whether the regional aggregate hides the response of the three existing
Dominion price references chosen for the Richmond investigation (ACCA, BASIN,
BELLWOOD). The rival is a broad solar/load
state or movement of the Western reference leg; the falsifier is disappearance of
local-versus-hub premiums when solar and local demand are similar. These names are
fixed prior project references, not newly selected strongest nodes or B endpoints.

The first screens are exploratory and informed this specification; neither the
already explored years nor the stricter match are a fresh confirmation sample.
Use labels 08–17, exact year-month/hour/week-type calendar, and complete common
support across displayed fundamentals/prices. Compare all daytime records with
calendar controls, then nearest three no-record controls within the same calendar
and fixed calipers: SOUTH solar ±500 MW and DOM demand ±2,000 MW; sensitivity ±250
MW/±1,000 MW. Rank squared scaled distances with timestamp-stable tie breaking;
require at least three candidates. Do not match on price, shadow or other outcomes.
A secondary context match retains the loose solar/DOM calipers and also requires
MIDATL demand ±2,000 MW and WEST wind ±1,000 MW, adding their squared scaled
distances before selecting three neighbors. It asks whether a wider regional
operating-state difference alone accounts for the local RT signature.

These differences are conditional actual-state diagnostics, not causal treatment
effects, issue-time forecasts or probabilities. Unmeasured weather, network state,
availability, remote demand and other constraints remain.

For each caliper retain both the nearer-control estimator and calendar controls
on exactly the same target records. This separates changed target support from
additional conditioning. Save all target/control timestamps, differences in
matching inputs, unique controls, dates, dropped target counts and matched sample
medians. Never claim matching covers all records: strict support is small and
March 2025 has little comparable no-record support. Check all years separately,
January–August only, and pool again without March 2025.

Use the established 599 whole-calendar-week resamples. Freeze the chosen neighbor
sets, but resample both target and control rows jointly and recompute each target's
weighted control mean; reuse of controls shares their week weight. Omit targets
whose control set has zero weight in that draw. Use the same draws for each metric,
including direct RT-minus-DA differences. Report approximate percentile intervals,
not independent-hour precision. Compare week and 14-day clustering on the pooled
nearer-control estimators. Intervals omit caliper choice, matching-search and
future-regime uncertainty. The strict/loose comparison is a sensitivity, not an
independent replication or an identified electrical effect.

Separate total LMP, congestion and marginal losses, and verify paired-price algebra.
Use each named bus minus DOMINION HUB. Keep DOM_RESID_AGG, DOMINION HUB minus WESTERN
HUB and aggregate minus Western for reference accounting; sums of point contrasts
are exact only on the same target/control support. A negative Western-relative
contrast does not establish that the local-versus-Dominion premium reversed.
Save full differences and display median/tail diagnostics so mean premiums do not
masquerade as typical-hour outcomes. Supplied shadow rank associations/bins, where
shown, describe co-movement, not signed electrical sensitivities or payout.

Sources are the existing D00 brief and D01/D02/D03/D04/D05 measurements,
paired prices A29/A32, mechanics P01/P06/P11,
T02's compatible-state/information discipline and ST01's dependence caution. No
new measurement acquisition or Zotero save is part of this test. Unknown B market,
clock, export completeness and signed equipment sensitivities remain material.

## Textbook-guided uncertainty extension (8 October 2026)

`--uncertainty-only` writes new research results to `results/short_case/tables/` and
`uncertainty.json`. It leaves canonical measurements and established base results
unchanged. Read [the textbook working memory](../docs/knowledge/uncertainty-textbook.md)
for the source, chapter scopes, decision sequence and limits. This is an empirical
extension, not a stochastic dispatch optimizer or a calibrated trading forecast.

Questions fixed before computation: (1) Do the previously specified joint states
change both supplied-row frequency and named price exposure? (2) How much do
record/no-record price distributions overlap in the current regime? (3) Do complete
delivery-hour price benchmarks differ from selected recorded hours? Rival explanations
remain capability, local availability, other constraints, weather and hourly combinations.
No new data or outcome-selected thresholds are acquired.

Reuse `prepare()` and its clock/entity/missingness rules. Joint states reuse the
original calendar medians, January-August comparison, first pair for each gate,
B's 08-17 labels, minimum three observations in every cell and common calendar
weights. A: PJM demand x WEST wind; B: SOUTH solar x local DOM demand;
C: WEST wind x Mid-Atlantic demand. Reconstruct weights as stratum size / cell
size. Require every frequency/support value to reconcile with saved joint results.
Extend the same retained actual-state samples to DA/RT total and congestion
spread means. For B, retain local-minus-Western, local-minus-Dominion and
Dominion-minus-Western separately. Mean intervals and all six paired cell
differences resample whole calendar weeks 599 times with fixed state labels and
weights. The fixed weights match the original joint-curve uncertainty convention;
they do not refit medians, infer cause, capture specification search or predict
future regimes. State support excludes weekends; do not extrapolate to off-peak.

Save empirical price distributions by gate, exact pair, DA/RT, total/congestion,
January-August year and supplied-row status. Use all eligible hours in each group,
no fitted density, clipping or normal assumption. Save mean, median, quantiles,
sign fractions, extrema and sample size. These raw distributions describe exposure
and overlap; their differences retain composition bias. Mean and median are not
interchangeable. A tail quantile describes realized hourly variability, not uncertainty
about the mean or monthly settlement risk.

For all three candidate exposures, build complete physical-UTC-hour DA research
benchmarks from the paired public price source, keeping repeated autumn hours.
Reuse and verify the saved holiday calendar and published hour classes: weekday
nonholiday starts 07-22 peak, every other hour off-peak. A uses BGE residual minus
Western peak (proxy, not BGE Zone); B Dominion Hub minus Western peak (diagnostic,
no verified desk ticket); C ComEd residual minus Western off-peak. Save all 32 monthly
means, equal-day sensitivity, physical-hour counts, monthly-mean empirical summary,
and January-August hourly distribution summaries. Monthly observation counts are
small, seasonal and nonstationary; they are not future scenario probabilities.
Require C monthly values to match the established reconstruction. Distinguish
physical-hour coverage from source-label record coverage.

On eligible record-join hours in each block, verify the descriptive identity
all-hour mean = row fraction x row-hour mean + absent fraction x absent-hour mean.
Keep excluded clock labels out of this identity and disclose their count. This
accounting identity assigns no anonymous-gate causal contribution and no profit.
Retain per-hour values for independent SQL verification and distributions.

Run `uv run python scripts/analyze_flowgates.py` from the project root. In the managed sandbox use `UV_CACHE_DIR=/private/tmp/pjm-analysis-uv MPLCONFIGDIR=/private/tmp/pjm-matplotlib uv run --no-sync python scripts/analyze_flowgates.py`, or `.venv/bin/python scripts/analyze_flowgates.py` with the existing environment.

## Why retain this method

The assessment needs separate answers about when records appear, what operating conditions accompany them, how expensive relief is, and how exact locations' prices separate. A fitted straight line or normal error model is not needed to answer these questions. This script retains empirical distributions, calendar-matched contrasts, nonlinear rank-bin curves, explicit condition combinations and cross-year price checks. It does not fit a forecast, assign physical line flows or infer causal effects. The book T02's reviewed risk passages motivate reporting typical values, mean outcomes and tails separately. The consolidated report cites the primary block-bootstrap reference for dependence, alongside PJM price/constraint definitions and ICE settlement specifications.

## Inputs and preparation

Read-only `data/pjm.sqlite`: `hourly_analysis`, entity-keyed `load`/`wind`, and current paired `pjm_multi_node_hourly_lmps`. Solar and fuel measurements are already in the checked hourly panel. Existing source registrations are D01–D06/B01 and A31/A32. The source clock and anonymous constraint market remain provisional. The user confirms complete binding-hour coverage and shadow averaging across the whole hour. The supplied RT prices are retained in SQLite but this analysis uses the public paired hourly A32 prices consistently; A28 is a distinct settled-price feed. Do not silently mix their observations.

A **recorded hour** is one supplied constraint row, not one distinct binding event, a full hour bound or an overload. The user confirms that absent rows are nonbinding hours and shadow values average across the entire hour. Recorded fractions count hours containing binding, not minutes bound. Exclude the five documented clock-change dates, retaining 23,256 source-hour labels per gate, with A/B/C 4,691/1,234/4,765 records. Missing fundamentals and absent-record shadows remain missing. Solar changes require complete consecutive non-clock-change labels at every intervening hour. A three-hour change is current output minus output three hours earlier, in MW over that interval, not MW/hour.

Source pivots verify unique hour/entity keys. Price nodes are paired on UTC; each eligible Eastern label is unique after clock-date exclusion. Calculate exact left-minus-right DA and RT total-LMP and congestion spreads: BGE_RESID_AGG, DOM_RESID_AGG and COMED_RESID_AGG versus WESTERN HUB. B also has DOM_RESID_AGG minus DOMINION HUB and DOMINION HUB minus WESTERN HUB. The latter two sum exactly to B's Western-relative spread. These are regional exposure diagnostics, not known constraint endpoints. ICE BGE Zone settlement is not verified by this BGE residual-aggregate series.

## Statistics

**Timing:** eligible-hour denominators by hour, month, weekday and season. Yearly hour/weekday/season comparisons use January–August only. In those comparisons winter is January–February, summer is June–August and autumn is absent; no complete-year seasonal equivalence is claimed. Monthly bars retain every observed month.

**Load timing context:** the local zone, PJM and one geographically relevant nonlocal region have separate matched contrasts by three dayparts, the four observed seasons and weekday/weekend. These points answer when a load association appears, rather than merely when the constraint is recorded. They are exploratory point comparisons with support counts in the table; no uncertainty interval is plotted. Observed-season coverage is unequal across years, and no autumn 2026 is available.

**Matched means:** for each measurement separately, use year-month × recorded hour × weekday/weekend. An eligible recorded hour is compared with the mean of at least three available absent-record controls in that calendar group. Weight retained recorded hours equally. Report available hours, matched record hours/dates, available controls and the two matched means. Controls can be reused across records. This controls calendar patterns, not demand/wind/solar simultaneously, network state, dispatch feedback or other constraints. Different measurements can have different support.

**Dependent uncertainty:** draw calendar Monday–Sunday weeks with replacement using NumPy's multinomial generator, 599 replicates and fixed seed 20261008. For each draw multiply all recorded/control observations in a week by its draw count, recompute the weighted absent-control mean in each originally eligible calendar group, then recompute the equally weighted recorded-minus-control contrast. A calendar group with no resampled controls is omitted in that draw; original eligibility (three controls) is fixed. Percentile 2.5/97.5 endpoints are approximate descriptive uncertainty intervals. No independent-hour, normal-error, p-value or causal confidence claim is made. Weeks are an arbitrary practical dependence scale: day and 14-day sensitivity intervals for each lead input and principal DA/RT spreads are saved separately. Dependence longer than the chosen blocks, nonstationarity and unusual regimes remain limitations. These intervals do not include specification-search uncertainty or predict an unseen regime.

**Nonlinear input curves:** rank each input within its exact calendar group using average ranks for ties; divide percentile ranks into five ordered bins. Retain only groups containing every bin. For each bin average that group's recorded fraction with identical group weights proportional to retained group size. This avoids imposing a linear relation and avoids comparing midday solar with midnight solar. Nighttime/tied solar and sparse strata can be excluded; available and retained hours are displayed. Week bootstrap uses the fixed bins and fixed per-observation standardization weights; it does not re-estimate bin boundaries. The bars therefore quantify observed variation under this specification. They are not conditional causal effects or calibrated forecast probabilities.

**Joint conditions:** above the exact-calendar median means higher; ties go to lower. Retain calendar strata with at least three observations in all four cells and use identical calendar weights across cells. This requirement necessarily excludes weekends in this sample. A compares PJM demand × WEST wind, plus evening local demand × three-hour solar drop; B compares daylight SOUTH solar × local demand and × Mid-Atlantic demand; C compares WEST wind × Mid-Atlantic demand and × ComEd demand. Show January–August years separately, with each cell's records/hours and total retained support. Changing year support and unmeasured conditions limit interpretation. Tables also contain week-bootstrap intervals using fixed cell definitions/weights.

**Generation:** shares are output divided by the total of all ten observed PJM fuel categories; require all ten measurements and preserve source values. Shares sum to 100%. Plot matched recorded/control mean shares and output differences separately. Whole-PJM actual dispatch is context, not local unit availability, transfer balance or proof of a generation cause. Dispatch can respond to binding.

**Distributions and shadows:** use SciPy's empirical CDF directly, with no fitted distribution, winsorization or removal of extremes. Save mean, median, p01/p05/p25/p75/p95/p99, min/max and positive/negative fractions. Empirical means matter for linear payoff; medians describe typical hours. The log-like display retains sign and extreme values. Shadows use supplied magnitude only during records, with original signed values unchanged in SQLite. Equal-count shadow quintiles show the median RT congestion spread and observed middle 50%; these bars are an IQR, not an uncertainty interval. Pooled shadow groups mix calendar regimes and constraints, and a shadow-price association is not an electrical sensitivity or tradable revenue.

**Price regimes:** all-hour monthly DA/RT total-spread means, January–August yearly matched DA/RT total/congestion differences, and shadow-group prices. B additionally exposes local-versus-hub RT congestion reference decomposition and the weaker Dominion Hub-minus-Western DA total comparison as a dashed line. A regional spread reversal cannot establish a reversal in physical flow on an anonymous line.

## Outputs and checks

`results/base_case/summary.json`; eight figures per gate under `figures/`; `tables/matched_contrasts.csv`, `driver_curves.csv`, `joint_conditions.csv`, `timing.csv`, `distributions.csv`, `year_prices.csv`, `shadow_to_price.csv`, `load_context.csv`, and bootstrap sensitivity; `statistics_checks.json` records join/count/missingness/fuel/spread algebra checks. The database is not mutated.

Checks verify eligible counts, unique gate/hour and node/hour keys, exact shadow magnitudes, missing absent shadows, complete paired price coverage, fuel share sums and B reference cancellation. An independent direct SQL/group-loop audit checks selected matched means and distribution quantiles. Inspect every generated figure. Preserved prior C severity/calibration failures, low-ComEd-load reversal, original counterexample and B's 2026 regional sign change are included in the consolidated report; these tests are not refitted here.

All specifications are retrospective and exploratory after earlier study of the whole sample. Multiple comparisons are not confirmatory discoveries. A physical mechanism remains conditional without historical relevant network limits/topology, signed sensitivities and local output/availability. Trade EV requires instrument-specific covered hours, issue-time forecasts, executable entry prices and costs; recorded-versus-absent mean differences are not profits.

## Targeted mechanism and model investigation (8 October 2026)

`--investigations-only` runs the additions below against the same read-only panel without recalculating the established base. A normal run also creates these outputs. No new measurement, clock rule, source price or absence definition is introduced.

**Questions fixed before calculation:** Does measured demand account for A's changed record rate, or does its mapping change? Does B's solar/price association survive omitting March 2025 and each year? Does wind add information for C occurrence and DA prices, including weekends? Can a price graph distinguish the local DOM pocket from Dominion Hub? Rival explanations include relevant availability/topology, other constraints, dispatch response, weather and export-definition changes. Data-center customer type, weather normalization and network state are absent; no load increase will be labeled data-center demand.

**Regime and robustness:** Compare January–August yearly counts. Standardize A load means over common month × hour × weekday/weekend cells with identical weights from 2024, separately all hours and overnight labels 0–5. These are actual loads, not weather-normalized growth. B's original calendar-matched estimator is repeated on all data, without March 2025, and without each year, for solar level/change and exact local/hub DA/RT price pairs. Exclusion results are retrospective sensitivity, not independent replications. C's price contrasts are repeated by weekday/weekend and year, retaining support. These weekday classes are operating diagnostics, not official contract calendars or monthly settlements.

**XGBoost and simple benchmarks:** Two chronological diagnostics: fit through 24 August 2025 and evaluate September–December 2025; fit through 24 December 2025 and evaluate January–August 2026. The seven-day separation limits adjacent-state leakage. Parameters are fixed before reading scores: 160 trees, depth 3, learning rate .05, minimum child weight 20, row/column subsampling .8, L2 5, histogram trees, two threads, seed 20261008. No random split, test-tuned threshold, class weighting, recalibration or search. Evaluate a training-rate constant, standardized logistic calendar/full-input models and XGBoost full/group-omission models. Five input groups: calendar; separate overlapping loads; regional wind; local-proxy solar level/one-/three-hour changes; whole-PJM gas/coal/nuclear MW. Exclude prices, shadows, record histories, other-gate rows and date/year identifiers from inputs. Use the same complete-case support for all variants and save excluded counts; source missingness is not filled. Logistic standardization is fitted only on training rows.

Record Brier (mean squared probability error), log loss, ROC AUC, average precision and mean prediction versus observed fraction. Omission means refit without a whole group: full versus no-solar tests added solar information, not solar causality. Correlated groups can substitute for each other; gain importance/SHAP is not treated as a causal contribution. Resample evaluation calendar weeks 599 times to describe uncertainty in the paired Brier difference (omitted minus full), retaining dependent losses. Those intervals omit specification search and future-regime uncertainty. Save decile calibration, monthly residuals and training-range support flags. Data outside a training range or a residual gap is diagnostic of missing/changing relationships, not proof of topology change.

**Separate DA price target:** Fit training-mean, standardized ridge/calendar, ridge/full and XGBoost/full and lead-input-omission regressors to every complete eligible hour's named DA total spread (A/C local minus Western; B Dominion Hub minus Western). Score MAE, RMSE, signed mean error and monthly mean error without clipping tails. This prevents occurrence skill from masquerading as payout skill. Actual operating inputs and final prices still make all scores retrospective diagnostics, not forecasts or ICE backtests. The previously explored 2026 period is not a fresh holdout.

**Graph theory application:** Read the existing seventeen named nodes, pair by UTC/entity and use eligible unique Eastern labels. For January–August 2026 DA and RT congestion separately, subtract each node's year-month × hour × week-type mean, then compute Spearman correlations on complete common observations. A complete undirected similarity graph has edge distance `sqrt(2*(1-rho))`; NetworkX's minimum spanning tree retains 16 edges connecting 17 nodes. Fixed node labels/layout and saved pair correlations allow inspection of DOM local/bus/hub differences. Recompute direct DOM-local/Dominion/Western correlations on 2024–2025 January–August support as a sensitivity. No gate selection, fitted causal arrows, geographical coordinates or physical branch is inferred. Edges measure price co-movement and can reflect shared constraints; common calendar removal is descriptive. An electrical graph would require historical bus/branch reactance, status, ratings, contingency mapping and signed PTDF/LODF sensitivities. Those fields are not acquired here.

**C complete-hour price benchmark:** Use all physical UTC price hours for COMED_RESID_AGG and WESTERN HUB, including the five clock-change dates, without joining anonymous records on those dates. Convert UTC to America/New_York and verify stored Eastern labels. Apply the published ICE hour classes: weekday non-NERC-holiday starts 07–22 are peak; starts 00–06 and 23 plus every weekend/holiday hour are off-peak. Retain the six NERC holiday dates for 2024–2026 in a saved calendar table. Compare hourly weighted and equally weighted daily means of the same named DA total spread by delivery month; each year's January–August summary weights actual hours. These are reconstructed research benchmarks, not official ICE settlements: COO and PJD descriptions differ in averaging wording, and historical terms, invoices, entry quotes and costs are not verified. Equal-day versus equal-hour sensitivity tests whether that averaging choice alters the descriptive discount; neither establishes EV. Source measurements and UTC keys are unchanged.

Outputs: `investigations.json`, `investigation_checks.json`, mechanism/model/regime/graph/block CSV tables, and seven figures: `a_regime`, `b_robustness`, `c_weekends`, `c_blocks`, `ml_occurrence`, `ml_prices`, `price_graph`. The report embeds these alongside the prior evidence and retains failed models and counterexamples.

Verification: the standard-library checker reconstructs all classifier Brier/mean-probability and price RMSE/mean-error scores from saved predictions, using the same double precision for probabilities and metrics. A separate read-only SQLite loop audit, without importing the analyzer, reconciles 497 scalar point/support results in `investigation_numeric_review.json`: yearly support, A standardized loads, non-ramp B exclusions, C weekday/weekend contrasts, and monthly/yearly physical-hour price benchmarks. It does not independently recalculate week intervals, B's ramp exclusions or official settlements. All seven new figures were visually inspected.

## A: test actual nearby generation before blaming retirements

The acquisition question, rivals and falsifier were recorded in `results/base_case/breakthrough_search.md` before requesting EPA data. Retrieve CAMPD apportioned hourly records for Brandon Shores (602) and Herbert A Wagner (1554), 1 January 2024 through 30 June 2026, including nonoperating hours. The quarterly cutoff avoids incomplete 2026 Q3. Preserve the response, query and hash outside canonical SQLite. These are candidate nearby plants, not identified endpoints or verified relieving injections for A.

EPA's CAMPD FAQ specifies local standard time and gross load in MW during operation. Multiply gross load by operating time to obtain MWh; assign zero only to an explicitly present zero-operating-time row. Missing gross load in an operating row remains missing. Wagner unit 2 lacks gross electrical measurements in all operating rows; its electrical output is unknown. Both electrical and steam fields are blank in the acquired response, so do not infer its reporting reason. Exclude it from the electrical subtotal and label the retained units 1/3/4. Verify complete six-unit hourly keys, no duplicates, operating-time bounds and missingness. Sum Brandon Shores' two units and the three identified Wagner electrical series separately, preserving incomplete subtotals.

Compare monthly gross energy divided by physical facility hours with A's monthly supplied-row fraction. Compare January–June years and April–June separately; these are descriptive levels, not causal effects. For the model diagnostic, convert Maryland's fixed UTC−5 clock to UTC and then Eastern prevailing labels. Exclude the established clock-change dates; preserve the anonymous clock qualification. Use the same preexisting inputs, fixed XGBoost parameters and seven-day chronological gap, adding only these two actual electrical-output subtotals. Compare constant, logistic and XGBoost with/without the unit group on identical complete support for September–December 2025 and January–June 2026. Also shift the unit timestamps ±1 hour as clock sensitivity. Save probabilities, scores and paired week-resampled differences; do not tune or recalibrate to 2026. Actual generation can respond to congestion; even better model error would not show that lost generation caused A or supply issued-time odds. A failure to explain the increase narrows the hypothesis, but does not establish topology or data-center causality.

The monthly screen then selected June as a transparent rival check: Brandon Shores has similar gross output in 2025/2026 while A's fractions differ greatly. This month was selected retrospectively, not independently of outcomes. Compare BC/PJM/DOM demand, WEST wind, A row fraction and the named BGE-minus-Western DA total spread using the same June hour × weekday/weekend weights from all 720 June-2025 labels. Each input uses its available measurements within all 48 cells, retaining counts. Demand has one missing label in each year. Unit comparisons use complete EPA standard-clock month averages, separately labeled; never call them aligned hourly injections. Include the measured Wagner subtotal's decline as a counterexample to unchanged total local supply. Plot percentage changes in separate inputs, row fractions and price means in separate panels. Retain the median and 95th percentile for the price distribution. Equal calendar weights do not match weather, hourly state distributions, plant availability or network state; a higher mean premium is not a futures payoff.

## Figure wording only (8 October 2026)

`render_local_supply_figures(result)` draws the two unit-output figures directly from the saved monthly, model-score and June tables in `local_supply.json`. It can refresh labels without acquiring data or refitting models. The June axis now says “Share of hours with an A record”; the footer spells out the identical time-of-day and weekday/weekend weighting and warns that operating conditions are not identical. Numerical values, model specifications, support and uncertainty calculations are unchanged.

## Price density views (user-requested, 8 October 2026)

`--density-only` reads the established eligible panel and two saved learning-report
hour tables. It adds density curves, exact empirical diagnostics and histogram
counts without changing measurements, matches, CDFs or existing estimates.
The fixed questions are whether A/C binding hours shift the common DA/RT price
range, whether B's local DA response differs from its hub response, whether B's
matched RT local premium extends beyond rare extremes, and how complete-block
hourly price concentrations change by year. No node or sample is selected by a
new result. Use January-August 2026 for raw gate comparisons, the existing pooled
504-target loose B match for named-bus differences, and January-August 2024/25/26
for complete physical-hour DA blocks.

A literal derivative of an empirical CDF is an atomic measure, not a useful smooth
curve. Estimate a descriptive density from all observations with SciPy
`gaussian_kde`. The Gaussian is the smoothing kernel, not an assumed normal price
law. Within each comparison use one common dollar bandwidth
`0.9 * min(pooled sample SD, pooled IQR / 1.349) * pooled_n**(-0.2)`.
Show half/default/double bandwidth sensitivity. This rule sets display resolution;
correlated hours do not become independent observations, confidence intervals or
future probabilities. Do not infer physical regimes from small density bumps.

Use a linear dollar axis and a shared central viewing window at the pooled 5th
and 95th percentiles. All prices, including outside-window extremes, enter every
kernel estimate. Do not renormalize the central view. Save and display each
sample's actual fraction outside the window and retain the full-support CDFs.
Overlay common 36-bin histogram densities: count/(full sample n * dollar width).
Curve height has inverse-dollar units; interval area is probability mass.
Exact counts, sign/range fractions, means, medians and tail contributions always
come from observations, not smoothed areas. Split sorted observations into the
bottom/top `ceil(0.05*n)` and remaining hours; each contribution is sum/n and
adds exactly to the original mean. The central-sample mean is a diagnostic only.
Inspect all curves and half/double-bandwidth mode movement, but base conclusions
on unsmoothed statistics. No causal effect, issued forecast, monthly settlement
risk or revised trade EV follows from re-expressing the same sample.

## Descriptive generation-trend extension — 9 October 2026

`results/new_data_review/generation/analyze.py` reads raw fuel/entity rows and gate
status in read-only SQLite, without changing this analyzer or its saved estimates.
Its methods define all-ten-fuel complete support, January–August common-calendar
background, year-specific target/control means and retained counts. A separate
raw-SQL/EPA audit checks the new arithmetic. Actual output is not availability
or a forecast. See [generation methods](../results/new_data_review/generation/methods.md).
