"""
Synthetic data generator for the Honeywell Agentic Supply Chain capstone.

Run once:  python generate_data.py
Outputs 6 CSVs into ./data/

Design notes (say these in the video, they are worth marks):
- We model SITES and PROCESSES as first-class entities, not just suppliers.
  Two "independent" Tier-1 suppliers can converge on the same accredited
  special-process house (heat treat / NDT). That hidden convergence is the
  single point of failure that supplier-level dashboards cannot see.
- Every part carries a Time-To-Survive (TTS) proxy = inventory days of cover.
  Every site carries a Time-To-Recover (TTR) estimate. Exposure exists
  wherever TTR > TTS. (Simchi-Levi et al., Risk Exposure Index, HBR 2014.)
"""

import os
import random
import numpy as np
import pandas as pd

random.seed(42)
np.random.seed(42)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(OUT, exist_ok=True)

# ----------------------------------------------------------------------
# 1. Suppliers
# ----------------------------------------------------------------------
COUNTRIES = [
    ("USA", 0.10), ("Mexico", 0.25), ("Germany", 0.12), ("Czechia", 0.18),
    ("India", 0.30), ("China", 0.45), ("Taiwan", 0.40), ("Japan", 0.15),
    ("Turkey", 0.50), ("Malaysia", 0.28), ("UK", 0.12), ("France", 0.14),
]

COMMODITIES = [
    "Precision Castings", "Forgings", "Machined Structures", "Bearings",
    "Electronic Components", "PCB Assemblies", "Seals & Gaskets",
    "Fasteners", "Wire Harness", "Sensors",
]

supplier_rows = []
for i in range(1, 31):
    country, geo_risk = random.choice(COUNTRIES)
    tier = 1 if i <= 18 else 2
    supplier_rows.append({
        "supplier_id": f"SUP-{i:03d}",
        "supplier_name": f"{random.choice(['Apex','Vertex','Northstar','Kestrel','Meridian','Orion','Bluewave','Pinnacle','Granite','Ironclad','Sable','Cobalt'])} "
                         f"{random.choice(['Forge','Castings','Precision','Industries','Aerospace','Components','Technologies','Metalworks'])}",
        "tier": tier,
        "country": country,
        "geo_risk_score": round(geo_risk + np.random.uniform(-0.05, 0.05), 2),
        "financial_health": round(np.random.uniform(0.35, 0.95), 2),   # 1.0 = strong
        "otd_pct": round(np.random.uniform(0.72, 0.99), 3),            # on-time delivery
        "quality_ppm": int(np.random.uniform(50, 4200)),
        "capacity_utilisation": round(np.random.uniform(0.55, 0.98), 2),
        "nadcap_certified": random.random() < 0.35,
        "annual_spend_usd": int(np.random.uniform(0.4e6, 22e6)),
    })
suppliers = pd.DataFrame(supplier_rows)

# ----------------------------------------------------------------------
# 2. Sites  (a supplier may have several; a site performs special processes)
# ----------------------------------------------------------------------
PROCESSES = ["Forging", "Investment Casting", "Heat Treatment",
             "Chemical Processing", "Non-Destructive Testing",
             "CNC Machining", "SMT Assembly", "Anodising"]

site_rows = []
sid = 1
for _, s in suppliers.iterrows():
    for _ in range(random.choice([1, 1, 2])):
        procs = random.sample(PROCESSES, k=random.choice([1, 2]))
        site_rows.append({
            "site_id": f"SITE-{sid:03d}",
            "supplier_id": s.supplier_id,
            "country": s.country,
            "city": random.choice(["Ogden", "Querétaro", "Pune", "Suzhou", "Brno",
                                   "Izmir", "Penang", "Nagoya", "Stuttgart",
                                   "Toulouse", "Sheffield", "Hsinchu"]),
            "processes": "|".join(procs),
            "hazard_score": round(np.random.uniform(0.05, 0.75), 2),
            "ttr_days": int(np.random.choice([14, 21, 30, 45, 60, 90],
                                             p=[.15, .2, .25, .2, .12, .08])),
        })
        sid += 1
sites = pd.DataFrame(site_rows)

# Deliberately plant a hidden convergence: force 3 sites to be the ONLY
# Nadcap heat-treat houses, and route many parts through them.
critical_sites = sites.sample(3, random_state=1).site_id.tolist()
sites.loc[sites.site_id.isin(critical_sites), "processes"] = "Heat Treatment|Non-Destructive Testing"
sites.loc[sites.site_id.isin(critical_sites), "ttr_days"] = [75, 90, 60]

# ----------------------------------------------------------------------
# 3. Parts
# ----------------------------------------------------------------------
PLATFORMS = ["APU-331", "Avionics-DAU", "Turbo-GT45", "BMS-Controller"]

part_rows = []
for i in range(1, 61):
    commodity = random.choice(COMMODITIES)
    unit_cost = round(np.random.uniform(4, 2600), 2)
    part_rows.append({
        "part_id": f"P-{1000+i}",
        "description": f"{commodity} item {i}",
        "commodity": commodity,
        "unit_cost_usd": unit_cost,
        "annual_volume": int(np.random.uniform(200, 40000)),
        "single_source": random.random() < 0.42,
        "qualification_lead_time_months": int(np.random.choice([3, 6, 9, 12, 18, 24],
                                                              p=[.1, .2, .25, .2, .15, .1])),
        "inventory_days_cover": int(np.random.choice([5, 10, 15, 20, 30, 45, 60],
                                                    p=[.1, .15, .2, .2, .15, .12, .08])),
        "requires_special_process": random.choice(
            ["Heat Treatment", "None", "None", "Non-Destructive Testing", "Anodising"]),
    })
parts = pd.DataFrame(part_rows)
parts["annual_spend_usd"] = (parts.unit_cost_usd * parts.annual_volume).round(0)
# TTS proxy = days of cover
parts["tts_days"] = parts["inventory_days_cover"]

# ----------------------------------------------------------------------
# 4. BOM  (part -> assembly -> platform)
# ----------------------------------------------------------------------
bom_rows = []
for _, p in parts.iterrows():
    for platform in random.sample(PLATFORMS, k=random.choice([1, 1, 2])):
        bom_rows.append({
            "part_id": p.part_id,
            "assembly": f"ASSY-{random.randint(10,49)}",
            "platform": platform,
            "qty_per_unit": random.choice([1, 1, 2, 4, 6]),
        })
bom = pd.DataFrame(bom_rows)

# ----------------------------------------------------------------------
# 5. Supplier-Part (the sourcing graph, incl. approved alternates)
# ----------------------------------------------------------------------
sp_rows = []
for _, p in parts.iterrows():
    n_sup = 1 if p.single_source else random.choice([2, 2, 3])
    chosen = suppliers.sample(n_sup)
    for j, (_, s) in enumerate(chosen.iterrows()):
        site = sites[sites.supplier_id == s.supplier_id].sample(1).iloc[0]
        sp_rows.append({
            "part_id": p.part_id,
            "supplier_id": s.supplier_id,
            "site_id": site.site_id,
            "is_incumbent": j == 0,
            "qualified": True if j == 0 else (random.random() < 0.55),
            "unit_price_usd": round(p.unit_cost_usd * np.random.uniform(0.88, 1.18), 2),
            "lead_time_days": int(np.random.uniform(21, 140)),
            "allocation_pct": 100 if n_sup == 1 else (70 if j == 0 else int(30 / (n_sup - 1))),
        })
supplier_parts = pd.DataFrame(sp_rows)

# ----------------------------------------------------------------------
# 6. Events  (the disruption feed the Risk agent senses)
# ----------------------------------------------------------------------
EVENT_TEMPLATES = [
    ("Fire", "Fire reported at {city} facility; production halted, extent unknown."),
    ("Labour Action", "Union strike notice served at {city} plant; walkout expected within 7 days."),
    ("Financial Distress", "Credit rating downgraded; supplier reports covenant breach."),
    ("Earthquake", "Magnitude 6.1 earthquake near {city}; structural assessment pending."),
    ("Port Congestion", "Container dwell times at nearest port up 240% week-on-week."),
    ("Export Control", "New export licensing requirement announced for this commodity."),
    ("Capacity Shortfall", "Supplier notified customers of allocation on {commodity} capacity."),
    ("Quality Escape", "Non-conformance batch identified; source inspection escalated."),
    ("Cyber Incident", "Ransomware disclosed; ERP and MES offline at {city}."),
]

event_rows = []
for i in range(1, 21):
    site = sites.sample(1).iloc[0]
    etype, tmpl = random.choice(EVENT_TEMPLATES)
    event_rows.append({
        "event_id": f"EVT-{i:03d}",
        "event_date": (pd.Timestamp("2026-07-10") - pd.Timedelta(days=random.randint(0, 21))).date(),
        "event_type": etype,
        "site_id": site.site_id,
        "supplier_id": site.supplier_id,
        "country": site.country,
        "severity": round(np.random.uniform(0.2, 1.0), 2),
        "source": random.choice(["Reuters", "Local Press", "D&B Alert",
                                 "Supplier Notice", "Customs Data", "Court Docket"]),
        "raw_text": tmpl.format(city=site.city, commodity=random.choice(COMMODITIES)),
    })
# Guarantee at least one high-severity hit on a critical convergence site
hit = sites[sites.site_id == critical_sites[0]].iloc[0]
event_rows.append({
    "event_id": "EVT-021",
    "event_date": pd.Timestamp("2026-07-09").date(),
    "event_type": "Fire",
    "site_id": hit.site_id,
    "supplier_id": hit.supplier_id,
    "country": hit.country,
    "severity": 0.95,
    "source": "Reuters",
    "raw_text": f"Major fire at {hit.city} heat treatment facility; Nadcap-accredited "
                f"lines offline. Company has not given a restart date.",
})
events = pd.DataFrame(event_rows)

# ----------------------------------------------------------------------
# 7. Master Production Schedule
# ----------------------------------------------------------------------
mps_rows = []
for platform in PLATFORMS:
    for m in range(1, 7):
        mps_rows.append({
            "platform": platform,
            "month": f"2026-{6+m:02d}",
            "planned_units": int(np.random.uniform(40, 260)),
            "margin_per_unit_usd": int(np.random.uniform(8000, 90000)),
            "customer_priority": random.choice(["High", "Medium", "Low"]),
        })
mps = pd.DataFrame(mps_rows)

for name, df in [("suppliers", suppliers), ("sites", sites), ("parts", parts),
                 ("bom", bom), ("supplier_parts", supplier_parts),
                 ("events", events), ("mps", mps)]:
    df.to_csv(os.path.join(OUT, f"{name}.csv"), index=False)
    print(f"  data/{name}.csv  ->  {len(df)} rows")

print("\nPlanted convergence sites (the hidden single point of failure):")
print(sites[sites.site_id.isin(critical_sites)][["site_id", "supplier_id", "city", "ttr_days"]].to_string(index=False))
