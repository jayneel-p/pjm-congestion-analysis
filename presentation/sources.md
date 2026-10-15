# Sources for the current presentation

The private GBE brief defines the required questions. The source CSVs supply anonymous constraints, regional load, solar, wind, fuel output and supplied real-time prices. They remain outside Git. Cleaning, clock alignment and row preservation follow the tracked processing methods, with no fabricated measurements.

Official PJM public price snapshots supply exactly named left-minus-right day-ahead and real-time total-price and congestion comparisons. Historical station observations and archived MOS runs support the weather research. Current weather is the saved 15 October snapshot for 16 October, rather than a newly acquired outlook. Contract values remain the 14 October worksheet. Original raw replies, issue times, sample identities and full numeric audits stay in the retained workspace.

## Market and forecast mechanics

- [PJM Load Forecasting](https://learn.pjm.com/three-priorities/planning-for-the-future/load-forecasting): targeted short-term weather-input passages. PJM demand forecasts already include weather.
- [PJM meteorologist account,20 May 2019](https://insidelines.pjm.com/accurate-load-forecasting-is-key-to-an-efficient-grid/): weather, demand and local renewable supply.
- [PJM Manual 14D](https://www.pjm.com/-/media/DotCom/documents/manuals/m14d.pdf), revision 71 effective 28 July 2026, sections 8.2.6/8.3 and 12.2.5/12.3: wind/solar forecast inputs and operational use. These are targeted sections, not a complete manual review.
- [PJM Data Miner API Guide](https://www.pjm.com/-/media/DotCom/etools/data-miner-2/data-miner-2-api-guide.pdf): official feed/metadata/filter conventions. Retained verified Zotero key C4F8TH6T.
- [PJM day-ahead prices](https://dataminer2.pjm.com/feed/da_hrl_lmps), [real-time prices](https://dataminer2.pjm.com/feed/rt_hrl_lmps), [load forecast](https://dataminer2.pjm.com/feed/load_frcstd_7_day), [wind forecast](https://dataminer2.pjm.com/feed/hourly_wind_power_forecast) and [solar forecast](https://dataminer2.pjm.com/feed/hourly_solar_power_forecast): exact source fields and saved timestamps are in the retained responses. Forecast creation time does not independently prove public receipt.
- [NOAA Model Output Statistics](https://www.noaa.gov/jetstream/upper-air-charts/weather-models/jetstream-max-model-output-statistics): archived MOS meaning and fields. Retained verified Zotero key PKQ9BGSQ. A six-hour release buffer remains an assumption.
- [National Weather Service API](https://www.weather.gov/documentation/services-web-api): saved grid/point forecasts. Grid forecasts at Richmond/Chicago city are distinct from historical airport observations.
- [ICE US power](https://www.ice.com/energy/electricity/us): product families. Exact PMN/PJL/NIC/PDO definitions, hours, fees and indicative margin were checked in the retained dated contract package. This general landing page alone does not verify the individual ticket. A's BGE Zone differs from its historical residual proxy; ComEd differs from NI settlement.

## Data and model boundaries

The tracked processing methods and aggregate presentation results define the comparisons. Same-hour actuals describe operating states. Issued forecasts enter only the retrospective chronological comparisons with inherited cutoff assumptions. The C wind-only failed benchmark predicts supplied shadow severity, not price. Hidden equipment, signed flows, local availability and executable quotes remain unverified. Historical price differences are neither line flow nor official contract profits.
