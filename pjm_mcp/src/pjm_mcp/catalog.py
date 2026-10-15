"""A small discovery aid; PJM metadata remains authoritative."""

GUIDE_URL = "https://www.pjm.com/-/media/DotCom/etools/data-miner-2/data-miner-2-api-guide.pdf"
CATALOG_REVIEWED = "2026-10-13"

# Short names checked against PJM's API guide, sections III and VIII.
FEEDS = (
    ("da_hrl_lmps", "Day-ahead hourly LMPs", "prices"),
    ("rt_hrl_lmps", "Real-time hourly LMPs", "prices"),
    ("rt_fivemin_hrl_lmps", "Real-time five-minute LMPs", "prices"),
    ("rt_da_monthly_lmps", "Settlements-verified hourly LMPs", "prices"),
    ("pnode", "Pricing nodes", "locations"),
    ("agg_definitions", "Fixed weighted-average aggregate definitions", "locations"),
    ("hrl_load_metered", "Hourly metered load", "load"),
    ("hrl_load_prelim", "Hourly preliminary load", "load"),
    ("inst_load", "Instantaneous load", "load"),
    ("load_frcstd_hist", "Historical load forecasts", "forecasts"),
    ("load_frcstd_7_day", "Seven-day load forecast", "forecasts"),
    ("hourly_wind_power_forecast", "Hourly wind power forecast", "forecasts"),
    ("hourly_solar_power_forecast", "Hourly solar power forecast", "forecasts"),
    ("wind_gen", "Wind generation", "generation"),
    ("solar_gen", "Solar generation", "generation"),
    ("gen_by_fuel", "Generation by fuel type", "generation"),
    ("frcstd_gen_outages", "Forecasted generation outages", "outages"),
    ("gen_outages_by_type", "Seven-day generation outages by type", "outages"),
    ("da_marginal_value", "Day-ahead constraint marginal values", "constraints"),
    ("rt_marginal_value", "Real-time constraint marginal values", "constraints"),
    ("da_transconstraints", "Day-ahead transmission constraints", "constraints"),
    ("rt_transn_constraints", "Real-time transmission constraints", "constraints"),
    ("act_sch_interchange", "Actual and scheduled interchange", "interchange"),
    ("transfer_limits_and_flows", "RTO transfer limits and flows", "interchange"),
    ("reserve_market_results", "Ancillary service market results", "reserves"),
)


def list_feeds(search: str = "") -> dict:
    """Search the bundled, non-exhaustive catalog without making an API request."""
    words = search.casefold().split()
    matches = [
        {"feed": feed, "title": title, "category": category}
        for feed, title, category in FEEDS
        if all(word in f"{feed} {title} {category}".casefold() for word in words)
    ]
    return {
        "feeds": matches,
        "count": len(matches),
        "scope": "Bundled starter catalog, not a live or exhaustive list of PJM feeds.",
        "reviewed_date": CATALOG_REVIEWED,
        "source": GUIDE_URL,
        "next_step": "Call get_feed_metadata. query_feed also accepts other PJM feed short names.",
    }
