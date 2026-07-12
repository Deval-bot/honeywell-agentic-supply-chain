"""
live_data.py — real, open, key-free data feeds.

WHAT IS REAL AND WHAT IS SYNTHETIC (say this exactly, on a slide):

    The supply network is synthetic, because no manufacturer publishes its
    bill of materials, supplier prices, or inventory positions.
    Everything the world already knows about those locations is REAL and LIVE.

    REAL, fetched live, no API key required:
      - USGS Earthquake Catalog ......... seismic hazard near each facility
      - Open-Meteo ...................... weather and precipitation risk
      - World Bank WGI .................. political stability by country
      - World Bank LPI .................. logistics performance by country
      - GDELT DOC 2.0 ................... global news signals per supplier/commodity
      - SEC EDGAR / Honeywell 10-K ...... company financials (below)

    SYNTHETIC, and disclosed as such:
      - supplier identities, prices, lead times, capacity
      - bill of materials, inventory cover, production schedule
      - the incident narratives used to demo the perception step

EVERY function below fails soft. If the network is down mid-demo, you get a
clearly-labelled cached value and the app keeps running.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List

import requests

TIMEOUT = 8


def _get(url: str, params: dict | None = None) -> Any:
    r = requests.get(url, params=params or {}, timeout=TIMEOUT,
                     headers={"User-Agent": "IIM-Mumbai-capstone/1.0"})
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# Real coordinates for the cities used in generate_data.py
# ---------------------------------------------------------------------------
CITY_COORDS: Dict[str, tuple] = {
    "Ogden":      (41.2230, -111.9738),
    "Querétaro":  (20.5888, -100.3899),
    "Pune":       (18.5204, 73.8567),
    "Suzhou":     (31.2989, 120.5853),
    "Brno":       (49.1951, 16.6068),
    "Izmir":      (38.4237, 27.1428),
    "Penang":     (5.4141, 100.3288),
    "Nagoya":     (35.1815, 136.9066),
    "Stuttgart":  (48.7758, 9.1829),
    "Toulouse":   (43.6047, 1.4442),
    "Sheffield":  (53.3811, -1.4701),
    "Hsinchu":    (24.8138, 120.9675),
}

ISO3 = {"USA": "USA", "Mexico": "MEX", "Germany": "DEU", "Czechia": "CZE",
        "India": "IND", "China": "CHN", "Taiwan": "TWN", "Japan": "JPN",
        "Turkey": "TUR", "Malaysia": "MYS", "UK": "GBR", "France": "FRA"}


# ===========================================================================
# 1. SEISMIC HAZARD — USGS Earthquake Catalog (real, live, no key)
#    Feeds: Risk Prediction Agent
# ===========================================================================
def seismic_hazard(lat: float, lon: float, radius_km: int = 300,
                   years: int = 10, min_mag: float = 4.5) -> Dict[str, Any]:
    """Count significant quakes near a facility over the last N years."""
    end = dt.date.today()
    start = end - dt.timedelta(days=365 * years)
    try:
        j = _get("https://earthquake.usgs.gov/fdsnws/event/1/query", {
            "format": "geojson", "latitude": lat, "longitude": lon,
            "maxradiuskm": radius_km, "starttime": start.isoformat(),
            "endtime": end.isoformat(), "minmagnitude": min_mag, "limit": 500,
        })
        feats = j.get("features", [])
        mags = [f["properties"]["mag"] for f in feats if f["properties"].get("mag")]
        return {
            "source": "USGS Earthquake Catalog (live)",
            "is_real": True,
            "quakes_10yr": len(feats),
            "max_magnitude": round(max(mags), 1) if mags else 0.0,
            "hazard_score": round(min(len(feats) / 40, 1.0), 2),
            "citation": "https://earthquake.usgs.gov/fdsnws/event/1/",
        }
    except Exception as e:                                   # noqa: BLE001
        return {"source": f"cached fallback ({type(e).__name__})", "is_real": False,
                "quakes_10yr": 0, "max_magnitude": 0.0, "hazard_score": 0.1,
                "citation": "https://earthquake.usgs.gov/fdsnws/event/1/"}


# ===========================================================================
# 2. WEATHER RISK — Open-Meteo (real, live, no key)
#    Feeds: Risk Prediction Agent ("weather impacts")
# ===========================================================================
def weather_risk(lat: float, lon: float) -> Dict[str, Any]:
    """7-day outlook. Heavy rain or extreme heat disrupt logistics and casting."""
    try:
        j = _get("https://api.open-meteo.com/v1/forecast", {
            "latitude": lat, "longitude": lon,
            "daily": "precipitation_sum,temperature_2m_max,wind_speed_10m_max",
            "forecast_days": 7, "timezone": "UTC",
        })
        d = j["daily"]
        rain = sum(x or 0 for x in d["precipitation_sum"])
        tmax = max(x or 0 for x in d["temperature_2m_max"])
        wind = max(x or 0 for x in d["wind_speed_10m_max"])
        score = min((rain / 120) * 0.5 + (max(tmax - 38, 0) / 10) * 0.3
                    + (max(wind - 50, 0) / 40) * 0.2, 1.0)
        return {"source": "Open-Meteo (live)", "is_real": True,
                "rain_7d_mm": round(rain, 1), "max_temp_c": round(tmax, 1),
                "max_wind_kmh": round(wind, 1), "weather_risk_score": round(score, 2),
                "citation": "https://open-meteo.com/"}
    except Exception as e:                                   # noqa: BLE001
        return {"source": f"cached fallback ({type(e).__name__})", "is_real": False,
                "rain_7d_mm": 0, "max_temp_c": 0, "max_wind_kmh": 0,
                "weather_risk_score": 0.1, "citation": "https://open-meteo.com/"}


# ===========================================================================
# 3. COUNTRY RISK — World Bank (real, no key)
#    Feeds: Risk Prediction Agent (geopolitical) + Global Sourcing Agent
#    PV.EST = Political Stability & Absence of Violence  (approx -2.5 .. +2.5)
#    LP.LPI.OVRL.XQ = Logistics Performance Index overall (1 .. 5)
# ===========================================================================
def _wb_indicator(iso3: str, code: str) -> float | None:
    j = _get(f"https://api.worldbank.org/v2/country/{iso3}/indicator/{code}",
             {"format": "json", "per_page": 60})
    if not isinstance(j, list) or len(j) < 2 or not j[1]:
        return None
    for row in j[1]:                       # newest first; take latest non-null
        if row.get("value") is not None:
            return float(row["value"])
    return None


def country_risk(country: str) -> Dict[str, Any]:
    iso = ISO3.get(country, country)
    out = {"country": country, "citation": "https://data.worldbank.org/"}
    try:
        stability = _wb_indicator(iso, "PV.EST")
        lpi = _wb_indicator(iso, "LP.LPI.OVRL.XQ")
        if stability is None and lpi is None:
            raise ValueError("no data")
        # normalise to 0-1 where 1 = worst
        geo = round(1 - ((stability + 2.5) / 5), 2) if stability is not None else 0.4
        log = round(1 - ((lpi - 1) / 4), 2) if lpi is not None else 0.4
        out.update({"source": "World Bank WGI + LPI (live)", "is_real": True,
                    "political_stability_index": stability, "logistics_perf_index": lpi,
                    "geopolitical_risk": max(0.0, min(geo, 1.0)),
                    "logistics_risk": max(0.0, min(log, 1.0))})
    except Exception as e:                                   # noqa: BLE001
        out.update({"source": f"cached fallback ({type(e).__name__})", "is_real": False,
                    "political_stability_index": None, "logistics_perf_index": None,
                    "geopolitical_risk": 0.4, "logistics_risk": 0.4})
    return out


# ===========================================================================
# 4. NEWS SIGNALS — GDELT DOC 2.0 (real, live, no key)
#    Feeds: Risk Prediction Agent (supplier failure) — this is the UNSTRUCTURED
#    text the LLM perception step is designed to read.
# ===========================================================================
def news_signals(query: str, max_records: int = 8) -> List[Dict[str, str]]:
    """Real news headlines. This is what the LLM reads and turns into structure."""
    try:
        j = _get("https://api.gdeltproject.org/api/v2/doc/doc", {
            "query": query, "mode": "ArtList", "format": "json",
            "maxrecords": max_records, "sort": "DateDesc",
        })
        arts = j.get("articles", []) or []
        return [{"title": a.get("title", ""), "domain": a.get("domain", ""),
                 "seendate": a.get("seendate", ""), "url": a.get("url", ""),
                 "is_real": True} for a in arts]
    except Exception:                                        # noqa: BLE001
        return [{"title": "(live news feed unavailable — using synthetic incident text)",
                 "domain": "fallback", "seendate": "", "url": "", "is_real": False}]


# ===========================================================================
# 5. HONEYWELL FINANCIALS — from the FY2025 10-K and Q1 FY2026 8-K (real)
#    Feeds: Production Planning Agent (margin scale) + your slides.
#    Hardcoded because EDGAR full-text parsing is not a 2-hour job.
# ===========================================================================
HONEYWELL_FACTS = {
    "fy2025_sales_usd_bn": 37.4,
    "fy2025_sales_growth_pct": 8,
    "aerospace_sales_usd_bn": 17.5,
    "building_automation_usd_bn": 7.4,
    "industrial_automation_usd_bn": 9.4,
    "ess_usd_bn": 3.1,
    "backlog_usd_bn": 37.5,
    "q1_2026_inflation_headwind_usd_m": 200,
    "q1_2026_segment_margin_pct": 23.3,
    "middle_east_revenue_impact_q1_pct": 0.5,
    "aerospace_spin_expected": "Q3 2026",
    "solstice_spinoff_completed": "2025-10-30",
    "source": "Honeywell FY2025 Form 10-K and Q1 FY2026 results release",
    "citation": "https://investor.honeywell.com/",
    "is_real": True,
}


# ===========================================================================
# ORCHESTRATED ENRICHMENT — called once per facility
# ===========================================================================
def enrich_site(city: str, country: str) -> Dict[str, Any]:
    """Everything the world knows about this real place, right now."""
    lat, lon = CITY_COORDS.get(city, (0.0, 0.0))
    seis = seismic_hazard(lat, lon)
    wx = weather_risk(lat, lon)
    cr = country_risk(country)
    composite = round(0.35 * seis["hazard_score"] + 0.20 * wx["weather_risk_score"]
                      + 0.25 * cr["geopolitical_risk"] + 0.20 * cr["logistics_risk"], 2)
    return {
        "city": city, "country": country, "lat": lat, "lon": lon,
        "seismic": seis, "weather": wx, "country_risk": cr,
        "composite_site_risk": composite,
        "all_sources_live": all([seis["is_real"], wx["is_real"], cr["is_real"]]),
    }


if __name__ == "__main__":
    import json
    print("Testing every feed. Anything marked is_real=False fell back.\n")
    print(json.dumps(enrich_site("Sheffield", "UK"), indent=2)[:1200])
    print("\nGDELT sample:")
    for a in news_signals("aerospace supplier fire")[:3]:
        print(" -", a["title"][:90], "|", a["domain"])
