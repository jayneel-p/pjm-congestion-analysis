# Presentation results

Visible text from the 37-slide presentation. These are dated research findings and conditional examples. Chart data remain editable inside the PowerPoint. Underlying measurements and full research reports stay outside this publication.

## Slide 1: C first, A needs more cash, B no bid

Conditional case for 16 October 2026. Price worksheet: 14 October. Forecast saved: 15 October.

Gate | Main finding | Conditional choice
A: Baltimore | Evening demand and a local price premium. | Buy BGE minus Western if price and cash qualify.
B: Richmond | Local prices rise, but the regional payment is unstable. | No bid under the dated estimate.
C: Chicago | Western wind and demand elsewhere fit a local discount. | Sell NI minus Western if price and cash qualify.

C is the first conditional choice. The entry price, cash and both contract legs must qualify.

Anonymous equipment and signed branch direction remain unverified. Exact contract and cash conditions are on slides 36–37.

## Slide 2: Binding and shadow prices

The supplied record describes a transmission limit. It does not give the power flowing on the line.

Measure | Meaning
Recorded hour | A supplied row means binding occurred during at least part of that hour.
No recorded row | Complete coverage is confirmed. Other eligible hours are nonbinding.
Shadow value | The value of easing a limit a little. The supplied value averages the whole hour.
Missing shadow | An absent record stays missing. It is different from a measured zero.

A row is not an overload, a separate event or a full hour bound. Shadow units, market, clock and exact aggregation implementation remain provisional.

## Slide 3: Prices and trade payments

Every price difference subtracts the second named place from the first.

Term | Meaning
Day-ahead and real-time | DA is set for the next day. RT is formed during delivery.
Total and congestion prices | Total includes energy, congestion and losses. Congestion is the part associated with delivery limits.
Price difference | First named place minus second. Positive means the first costs more; negative means it is cheaper.

The payment depends on the specified price difference, hours and quantity.

A/C use specified DA-settled indices. B compares an RT difference with the earlier DA difference. Historical shadows and price gaps are not trade profits.

## Slide 4: Source checks and cleaning

Six supplied time-series files. No measured numeric values changed.

Check | What we did
Keys and identifiers | Checked unique, nonmissing keys. Kept node IDs as text.
Text and dates | Checked spaces, parsed dates and sorted by key. No text cells needed whitespace correction.
Gaps and extremes | Kept missing values, negative prices, negative renewable readings and spikes. No filling or clipping.

All 2,089,376 rows survived cleaning. We kept negative values, spikes and missing readings.

Fresh raw/processed comparison: zero rows removed, zero measured numeric changes, zero duplicate keys and zero null key cells.

## Slide 5: Hour and location alignment

Cleaning a field and aligning its time are separate steps.

Input / check | Alignment rule
Load and supplied prices | Hour ending 1 becomes 00:00. Hour ending 24 becomes 23:00.
Fuel, constraints, solar and wind | Labels already use 0–23. These hours are not shifted.
Clock changes | Exclude five documented dates from source-label comparisons. Public prices retain UTC and node keys.
Join and coverage | Join hour and entity. The panel keeps all 10,732 constraint records. Missing readings and absent shadows stay missing.

After clock-date exclusions: 23,256 eligible labels per gate and 10,690 binding records. Source clock and market authentication remain provisional.

## Slide 6: Hot days have higher local demand

Actual daily blocks, compared with milder days in the same year-month and weekday/weekend class.

Hot days minus milder days
Axes: ; Extra demand (GW)

Demand is higher by 0.98 GW near A, 1.78 GW near B and 2.27 GW near C. These measured comparisons show the pathway, without becoming forecast adjustments.

Hot/mild block means: at least 25°C versus 18–23°C. Supported hot days: A 72/172, B 93/254, C 32/34. Actuals, 2024–August 2026.

## Slide 7: Weather adds information before demand enters

January–August 2026. Each model uses the same dates and delayed price history.

Price forecast error: lower is better
Axes: ; Error ($/MWh)

PJM demand forecasts already use weather. For C, adding weather cuts error by 21% before demand enters and 3% after demand enters.

Lower RMSE is better and gives large misses extra weight. A/B 171 dates, C 241. Previously explored periods. C fails the July–August comparison.

## Slide 8: A: binding is most common in evening labels

January–August in each year. Share of eligible hours containing binding.

Hours containing binding: time groups
Axes: ; Share of eligible hours

Label 20 reaches 57.4% in 2026. Summer is more active than winter, but calendar patterns alone do not identify the cause.

2026: Sunday 46.6%, Monday 41.1%; summer 56.5%, winter 15.5%. Supplied source clock labels remain provisional.

## Slide 9: A: wider demand rises in binding hours

Binding hours compared with nonbinding hours in similar calendar conditions.

Demand: binding minus similar hours
Axes: ; Difference in demand (GW)

PJM demand is 2.52 GW higher. The local BC difference is only 0.11 GW. Wider demand can increase the need for delivery into the area.

4,286–4,287 matched binding hours. BC, PJM, MIDATL and DOM overlap and are not added.

## Slide 10: A: sunset alone does not explain binding

MIDATL solar level and changes, plus WEST wind. Binding minus similar hours.

Renewables: binding minus similar hours
Axes: ; Difference (MW)

Solar differences are small and uncertain. Lower western wind can require replacement supply, but low wind is not a stable rule for A.

4,294 matches. Solar level −22 MW; 1h change +4 MW; 3h change +10 MW. All solar week ranges include zero. WEST wind −359 MW.

## Slide 11: A: gas and coal output are higher

Whole-PJM actual fuel output. Percentages below fuel names are binding-hour shares.

PJM fuel output and shares
Axes: ; Average output (GW)

Gas and coal rise while nuclear changes little. This can be a response to tight conditions. It does not show that a nearby plant disappeared.

4,291 matches. Mean hourly shares: gas 42.3%, nuclear 31.0%, coal 15.6%. Output is different from available capacity; Brandon Shores still ran.

## Slide 12: A: Baltimore prices separate from Western

BGE_RESID_AGG minus WESTERN HUB. Total and congestion prices, DA and RT separately.

Past prices: binding and similar hours
Axes: ; Price difference ($/MWh)

The DA total difference is $10.13/MWh larger in binding hours. RT congestion is $18.46 higher. Costlier delivery into Baltimore fits the pattern.

Binding versus calendar controls. Other constraints and losses also affect prices. BGE residual is a historical proxy for the contractual BGE Zone.

## Slide 13: A: warmth and falling solar can tighten delivery

Saved 16 October outlook. Baltimore peak block: average 72.5°F, maximum 82°F.

Forecast fact | Why it matters
Mid-Atlantic demand | Rises from 29.1 GW at 14:00 to 31.8 GW at 18:00.
PJM utility solar | Falls from 8.0 GW to 0.45 GW over those hours. Other supply must cover fading output.
Both price legs | More local supply, easier delivery or a larger Western price rise can reduce the Baltimore premium.

Warmth can raise cooling needs. Demand stays high as solar falls. If nearby supply or delivery is tight, BGE Zone can cost more relative to Western Hub.

These are different footprints and cannot form a local power balance. PJM demand already includes weather. The current block is below the historical hot-block threshold.

## Slide 14: A: what the purchase gains or loses

Example: buy BGE minus Western at $17/MWh. 80 MWh and $3/MWh costs.

Final difference | Net package cash | Result
$9/MWh | −$880 | Loss
$20/MWh | $0 | Costs covered
$25/MWh | +$400 | Gain

At $20/MWh, entry and costs are covered. A higher final difference gives a gain.

Teaching prices, not quotes. The full 07:00–23:00 block sets payment. The dated entry limit remains $17.10/MWh, with a chosen $5 mean-error allowance.

## Slide 15: A: confidence and what to watch

Moderate support for the demand/premium pattern. Low confidence in the hidden cause and signed branch direction.

Question | Answer
Main rival | Less useful delivery, imports or nearby available generation can produce a similar premium.
Counterexample | June demand was lower despite more binding, while Brandon Shores continued producing power.
What would weaken the view? | At similar demand, easier delivery without a narrower premium would weaken the delivery-pressure explanation.
Advance watchlist | Issued BC/PJM/DOM demand, solar decline, wind, nearby availability and delivery capability.

The watchlist has no reliable advance binding odds. Same-hour actuals describe states, not causes or advance forecasts.

## Slide 16: B: mainly midday, with changing seasons

January–August in each year. Share of eligible hours containing binding.

Hours containing binding: time groups
Axes: ; Share of eligible hours

Labels 10–15 form the main window. Spring activity weakens sharply in 2026, so a fixed spring rule fails.

2026 labels 11/12 each 12.4%; Tuesday 4.4%, Sunday 1.6%. Spring: 16.8% in 2025, 2.2% in 2026. Source clock provisional.

## Slide 17: B: local and wider demand are higher

Binding minus nonbinding hours in similar calendar conditions.

Demand: binding minus similar hours
Axes: ; Difference in demand (GW)

DOM demand is 0.42 GW higher and PJM demand 3.78 GW higher. Higher demand can increase the need for supply and delivery into the costly local area.

1,173 matched binding hours. MIDATL is 1.96 GW higher. Regional footprints overlap and are not added.

## Slide 18: B: more solar changes where power enters

SOUTH solar level and hourly changes, plus WEST wind.

Renewables: binding minus similar hours
Axes: ; Difference (MW)

Solar is 413 MW higher and its three-hour change is 105 MW larger. Solar may replace a plant that eased B. A nighttime record shows solar is unnecessary.

1,178 matches. The 1h change is near zero. WEST wind +409 MW; SOUTH wind is uncertain. The electrical sign on the hidden line is unknown.

## Slide 19: B: gas output rises

Whole-PJM actual fuel output. Percentages below fuel names are binding-hour shares.

PJM fuel output and shares
Axes: ; Average output (GW)

Gas rises, while coal and nuclear differences are uncertain. These whole-system values do not measure available supply near Richmond.

1,178 matches. Gas output +1,648 MW. Mean shares: gas 41.1%, nuclear 29.9%, coal 15.4%.

## Slide 20: B: the local area costs more than its hub

DOM_RESID_AGG minus DOMINION HUB. DA and RT total/congestion comparisons.

Past prices: binding and similar hours
Axes: ; Price difference ($/MWh)

A local premium fits limited access to the costly area. The later regional payment still depends on how much this difference grows after DA prices are set.

1,178 calendar matches. The wider local-minus-Western RT comparison changes sign in 2026. The pooled DA hub-discount range includes zero.

## Slide 21: B: fixed local buses retain a larger RT premium

ACCA, BASIN and BELLWOOD minus Dominion Hub at similar SOUTH solar and DOM demand.

Extra congestion price in similar hours
Axes: ; Extra difference ($/MWh)

The local RT congestion increases are much larger than the DA increases. The regional average is weaker, so a local price effect cannot replace the regional ticket.

Coverage: 504/1,139 daytime records; only 44 with four inputs. March has little comparable support. These buses are references, not identified endpoints.

## Slide 22: B: heat matters, but the price difference must rise further

Richmond averages 81.2°F and reaches 88°F. Six proposed hours: 10:00–16:00 Eastern.

DA difference | RT difference | Cash before fees
$5/MWh | $0/MWh | −$30
$5/MWh | $5/MWh | $0
$5/MWh | $15/MWh | +$60

Heat raises demand. Sunshine adds solar and can tighten or ease delivery into Richmond. Expected heat may already be priced. The bid pays the RT difference minus the DA difference.

Teaching example: all six 1-MW hourly bids selected. Actual payment uses accepted hours. The complete weather snapshot arrived after B’s auction. Dated estimate −$1.29: no bid.

## Slide 23: B: confidence depends on local support

The local RT pattern has support. The anonymous electrical cause and regional gain remain uncertain.

Question | Answer
Candidate direction | Delivery from the wider Dominion area into the costly Richmond-area pocket.
Rivals and support | Plant dispatch, network state and other limits can matter. Few similar hours, especially in March, limit coverage.
What would weaken the view? | A clock correction removing the premium, or measured injection/flow effects opposing the proposed direction.
Advance watchlist | SOUTH solar and changes, DOM/MIDATL demand, WEST wind, local available supply and delivery.

Later DA bus prices may update the intraday view, but cannot inform an earlier auction bid. No reliable advance warning odds are supplied.

## Slide 24: C: binding is common before dawn

January–August in each year. Share of eligible hours containing binding.

Hours containing binding: time groups
Axes: ; Share of eligible hours

Labels 04–07 stand out. Winter leads in 2026, while summer led in 2024. The seasonal pattern changes.

2026 label 06: 55.4%; Sunday 52.0%, Monday 38.0%; winter 50.3%, summer 17.1%. Source clock remains provisional.

## Slide 25: C: low local demand is not required

Binding minus nonbinding hours in similar calendar conditions.

Demand: binding minus similar hours
Axes: ; Difference in demand (GW)

MIDATL demand is 1.24 GW higher. ComEd’s −0.06 GW difference is uncertain. Demand elsewhere can matter without unusually low local demand.

4,359 matches. PJM +2.80 GW. ComEd week range −0.236 to +0.085 GW. Regions have different footprints.

## Slide 26: C: western wind is the main renewable clue

WEST solar and changes, plus WEST wind. Binding minus similar hours.

Renewables: binding minus similar hours
Axes: ; Difference (MW)

WEST wind is 788 MW higher. Solar is a secondary clue. Extra western supply can create outward delivery pressure when demand elsewhere needs power.

4,356–4,361 matches. Solar level and 1h change are uncertain; 3h change −40 MW, week range −71 to −10 MW. WEST output does not measure ComEd exports.

## Slide 27: C: fuel differences are uncertain

Whole-PJM actual fuel output. Percentages below fuel names are binding-hour shares.

PJM fuel output and shares
Axes: ; Average output (GW)

The mix describes the broader system. It does not locate available generation behind C or identify a plant outage.

Mean shares: gas 41.1%, nuclear 32.0%, coal 16.4%. Gas, coal and nuclear MW differences are uncertain.

## Slide 28: C: Chicago prices are cheaper relative to Western

COMED_RESID_AGG minus WESTERN HUB. DA and RT total/congestion separately.

Past prices: binding and similar hours
Axes: ; Price difference ($/MWh)

Binding hours have a DA total difference $16.63/MWh lower and RT congestion $30.35 lower. Limited outward delivery fits that discount.

Discounts also occur without C. These prices do not identify its line flow or isolate its cause. The proposed contract settles at NI Hub, not ComEd residual.

## Slide 29: C: windy weather tracks western wind output

Actual Chicago airport ground wind and WEST generation, 967 overnight daily blocks.

Windy weather brings more wind output
Axes: Chicago airport ground wind (mph); WEST wind output (GW)

The connection stays positive in all three years. Windy weather is useful supply evidence, while its price effect also depends on demand and delivery.

Raw rank correlation +0.754; calendar-adjusted +0.698. Actual observations do not calibrate tomorrow’s fleet output from one ground station.

## Slide 30: C: cool, windy weather can support the sale

Chicago averages 57°F with about 20 mph ground wind. Proposed NI-minus-Western sale.

Final difference | Net package cash | Result
−$13/MWh | +$250 | Gain
−$8/MWh | $0 | Costs covered
+$5/MWh | −$650 | Loss

Mild weather can limit cooling needs and wind can add western supply. If delivery out is tight, NI can remain cheaper. Less wind, more local demand or easier delivery can shrink the discount.

Teaching sale at −$5/MWh, 50 MWh and $3/MWh costs. The issued 9 GW wind quantity is PJM-wide. Current unusually high remote demand remains unproved.

## Slide 31: C: confidence and what to watch

Moderate support for the wind/demand/discount pattern. Low confidence in the hidden line and signed flow.

Question | Answer
Candidate direction | Outward delivery from wind-rich western supply toward demand elsewhere.
Counterexamples | Discounts occur without C. A wind-only shadow-severity model failed its benchmark; it was not a price-model test.
What would weaken the view? | Wind easing the identified limit, or easier delivery without a narrower discount.
Advance watchlist | Forecast WEST wind and MIDATL demand with ComEd demand, local availability and outward delivery.

The current wind forecast covers all PJM. Demand elsewhere is not shown unusually high for this date. Available plants, imports and other constraints remain rivals.

## Slide 32: Weather saved for the exact proposed hours

16 October forecast saved 15 October. NWS grid updates: 05:56–10:53 Eastern.

Place / hours | Temp °F mean (max) | Humidity / cloud % | Wind mph
Baltimore 07–23 | 72.5 (82) | 80 / 52 | 10.3
Richmond 10–16 | 81.2 (88) | 61 / 24 | 11.3
Chicago 00–07; 23–24 | 57.3 (62) | 87 / 87 | 19.6
Pittsburgh 07–23 | 61.9 (70) | 90 / 73 | 14.7

The full snapshot finished at 11:01 Eastern, after B’s 11:00 auction. Richmond/Chicago forecast grids are city points, distinct from historical airports.

## Slide 33: Demand and renewable forecasts across the day

16 October. PJM evaluations on 15 October: demand 10:47, wind 10:50, solar 10:00 Eastern.

Demand and renewable forecasts
Axes: Hour starting, Eastern; Average power (GW)

Demand stays high as utility solar falls. Wind continues overnight. Each curve covers its own region, so overlapping or different footprints cannot be added or netted.

All 24 hours retained. MIDATL peak 31.812 GW; DOM 19.254 GW. Utility solar and customer solar stay separate. Weather supports the explanation without repricing the dated worksheet.

## Slide 34: A: average gains hide frequent losses

80 MWh bought at the valid $17.10/MWh limit. Costs $3/MWh. Earlier forecast errors applied to the dated estimate.

A: 80 MWh bought at $17.10
Axes: Cash after costs ($); Share of outcomes at or below

The curve shows the share of outcomes at or below each cash amount. A has a positive mean but loses in 63.3% of these scenarios because large gains lift the average.

128 errors. Mean +$403, middle −$470. Worst 5% average −$3,375. Scenario shares are not reliable future odds or maximum losses.

## Slide 35: C: smaller losses still matter

50 MWh sold at the valid −$4.85/MWh limit. Costs $3/MWh. Earlier forecast errors applied to the dated estimate.

C: 50 MWh sold at −$4.85
Axes: Cash after costs ($); Share of outcomes at or below

The middle outcome is +$229 and the loss share is 23.9%. If the final gap averages about $5/MWh higher, C loses its estimated edge.

180 errors. Mean +$251. Worst 5% average −$641. Longer histories can remove the estimated gain. These are constructed scenarios, not guaranteed probabilities.

## Slide 36: C: exact price, contracts and cash conditions

16 October DA NI Hub minus Western Hub. Update the comparison after target prices publish.

Condition | One C package
Contracts and energy | Sell 10 NIC / buy 1 PDO. Matched quantity: 50 MWh.
Eastern hours | 00:00–07:00 and 23:00–24:00 on the same delivery date.
Entry price | NI bid minus Western ask at least −$4.85/MWh. Dated final estimate −$12.88.
Cash example | Indicative margin $2,692 plus chosen loss reserve $6,642.50 = $9,334.50.

Costs $3/MWh and chosen $5 mean-error allowance. Reserve assumes a +$125/MWh final difference; losses can be larger. Entry cutoff 15 Oct 18:00 NY / 16:00 Edmonton.

## Slide 37: A needs more cash; B remains no bid

A: BGE Zone minus Western Hub, peak hours. All values remain the 14 October worksheet.

Condition | A package / B decision
A contracts and hours | Buy 1 PMN / sell 5 PJL. 80 MWh, 07:00–23:00 Eastern.
A entry price | BGE ask minus Western bid no more than $17.10/MWh. Dated final estimate +$25.14.
A cash example | Margin $21,940 plus chosen reserve $9,608 = $31,548.
B decision | DOMINION HUB to DOM_RESID_AGG, six 1-MW hours 10:00–16:00. Estimate −$1.29 is below the +$10 rule. No bid.

A reserve assumes a −$100/MWh final difference; losses can be larger. A/C cutoff 15 Oct 18:00 NY. B auction 11:00. A bid cap does not limit later losses.
