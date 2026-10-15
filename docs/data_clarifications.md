# Confirmed hourly definitions and remaining source questions

The user confirmed on 8 October 2026 that the export covers binding hours and that each supplied shadow value averages across the whole hour, including nonbinding intervals. We use that clarification in the active reports. The original CSVs and calculations are unchanged.

## What an hourly record means

A row means the constraint bound during at least part of that hour. No row means it did not bind during that eligible hour. The recorded fraction is therefore the **fraction of hours containing binding**, not the fraction of elapsed time spent bound. Twenty recorded hours out of one hundred eligible hours means binding occurred in twenty hours. Those hours could contain different numbers of binding minutes.

The hourly shadow average combines intensity and duration. For illustration, five minutes at −120 and fifty-five minutes at zero average to −10 over the hour. Sixty minutes at −10 give the same average. The hourly data alone cannot distinguish those cases. Absolute hourly shadow magnitude measures the average marginal relief cost over the hour; it does not recover binding-minute intensity or duration. Missing supplied shadows remain missing in storage; we do not manufacture observed zero values.

A row is not a distinct physical event or an overload. One binding episode can continue across several hours, and several short intervals can fall inside one hour.

## Questions still unresolved

| Question | Why it matters | Current handling |
| --- | --- | --- |
| Are A/B/C records DA or RT, and what monitored equipment/contingency does each label represent? | Prices and dispatch differ by market; an anonymous name may cover more than one constraint definition. | Compare both markets and retain competing physical explanations. |
| What are the shadow units, sign convention and exact aggregation implementation? | Whole-hour averaging is confirmed, but interval weights, rounding and any aggregation across rows/contingencies are not documented. | Preserve signed values; use absolute magnitude for the hourly distribution. Do not infer flow or a nodal payout from the sign. |
| What timezone and start/end convention applies to each supplied file? | An hour shift can change ramp and price associations. | Retain the checked normalization, exclude five clock-change dates in source-label joins and preserve public UTC/node keys. |

## Hour alignment

Constraints, renewables and fuel use 0–23 labels and are not shifted. Load and supplied RT price hour-ending labels use 1–24 and are shifted down one hour. This reproduces the original checked panel. It does not independently verify the anonymous constraint's clock. Public price Eastern labels are supported by their explicit UTC conversion and retained import audit; broad clock shifts are not a justified fix.

Excluded dates are March 10 and November 3, 2024; March 9 and November 2, 2025; and March 8, 2026. The supplied calendar has 23,373 distinct naive labels, while complete public prices have 23,375 physical UTC hours per node. After the date exclusions, 23,256 eligible labels per gate are available. Do not discard repeated UTC hours from source price storage or join ambiguous Eastern labels.

The [retained price-clock comparison](../results/base_case/prior_evidence/price_clock_comparison.csv) and [panel methods](../scripts/build_hourly_panel.md) preserve the checked rationale. A confirmed source clock could alter timing/ramps and record-price joins; rerun the same explicit specifications if it changes.

## Measurements and geography

The load table contains overlapping RTO, regional and zonal footprints. Solar/wind regions are broader than the candidate local load zones; their subtraction is not measured local net load or export. Fuel dispatch is whole-PJM actual output, not historical local unit availability. The August 2026 capacity inventory was not a historical dispatch input and is retired from active analysis.

The brief attributes fuel data to EIA, while the supplied schema resembles PJM; exact lineage needs confirmation. Missing fuel hours stay missing. All ten observed fuel categories are required for a computed share denominator. Small negative renewable observations and economically important price tails are preserved.

The location hints suggest candidate territories, not constraint endpoints. A regional premium/discount does not establish signed flow on anonymous equipment. Relevant network limits, topology, contingencies, local availability and sensitivities are needed to test the physical stories.

## Prices and information timing

The report consistently uses seventeen-node public paired DA/RT prices: A29 DA and A32 RT, retrieved October 7, 2026. The supplied D06 RT feed and four-node settled A28 feed remain separate preserved sources; their values must not be silently substituted. Differences between feeds do not identify which anonymous constraint caused a spread.

Spreads always mean the first named location minus the second, separately for total LMP and congestion. A compares BGE_RESID_AGG with WESTERN HUB; B adds DOM_RESID_AGG minus DOMINION HUB and DOMINION HUB minus WESTERN HUB; C compares COMED_RESID_AGG with WESTERN HUB. None is a known line-endpoint pair.

Retrospectively retrieved final prices and same-hour actual load/renewables do not supply predecision publication vintages. The analysis measures associations, not a tradable forecast. For ICE, verify actual location, DA/RT market, hour block, month, MWh and official averaging. BGE Zone differs from the measured BGE aggregate; B's current ticket remains unverified. Option expiry references and futures exercise also differ by product. The EV examples are invented teaching states, not estimated profits.
