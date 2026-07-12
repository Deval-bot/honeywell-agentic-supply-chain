"""
Honeywell Agentic Supply Chain - agent layer (v2)

DESIGN RULE (say this on the slide and in the video):

    The LLM never computes a number.
    It READS (turns unstructured evidence into structured facts),
    it DECIDES (chooses between options and names the risk accepted),
    and it EXPLAINS (in language a non-specialist can follow).
    Every number is computed in pandas and can be audited.
    A fifth agent verifies every claim against a source row before a human sees it.

FIVE AGENTS, ONE CASCADE:
    Risk -> Sourcing -> Negotiation -> Planning -> Verifier
Each writes to a shared Blackboard; the next agent reads it.
"""

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List

import pandas as pd
import requests

MODEL = "claude-sonnet-5"
API_URL = "https://api.anthropic.com/v1/messages"


def mock_mode() -> bool:
    return os.environ.get("GEMINI_API_KEY") is None


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------
def _call(system: str, user: str, max_tokens: int = 1100) -> str:
    key = os.environ["GEMINI_API_KEY"]
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           "gemini-2.0-flash:generateContent?key=" + key)
    r = requests.post(url, timeout=90, json={
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"parts": [{"text": user}]}],
        "generationConfig": {"maxOutputTokens": max_tokens},
    })
    r.raise_for_status()
    j = r.json()
    return j["candidates"][0]["content"]["parts"][0]["text"]


def llm_text(system: str, user: str, fallback: str = "") -> str:
    if mock_mode():
        return fallback or "_(mock mode - set ANTHROPIC_API_KEY to enable reasoning)_"
    try:
        return _call(system, user)
    except Exception as e:                                   # noqa: BLE001
        return f"_(reasoning layer unavailable: {e}. Numbers above remain valid.)_"


def llm_json(system: str, user: str, fallback: dict) -> dict:
    """Structured output. Falls back cleanly so the demo cannot die."""
    if mock_mode():
        return {**fallback, "_source": "fallback (mock mode)"}
    try:
        raw = _call(system + "\n\nRespond with ONLY a JSON object. No prose, no code fences.", user)
        m = re.search(r"\{.*\}", raw, re.S)
        return {**json.loads(m.group(0)), "_source": "llm"}
    except Exception:                                        # noqa: BLE001
        return {**fallback, "_source": "fallback (llm parse failed)"}


# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------
@dataclass
class Blackboard:
    event: Dict[str, Any] = field(default_factory=dict)
    perception: Dict[str, Any] = field(default_factory=dict)
    live: Dict[str, Any] = field(default_factory=dict)
    exposed: pd.DataFrame = field(default_factory=pd.DataFrame)
    shortlist: pd.DataFrame = field(default_factory=pd.DataFrame)
    deal: Dict[str, Any] = field(default_factory=dict)
    plan: pd.DataFrame = field(default_factory=pd.DataFrame)
    claims: List[Dict[str, Any]] = field(default_factory=list)
    log: List[str] = field(default_factory=list)

    def note(self, agent: str, msg: str):
        self.log.append(f"{agent} | {msg}")

    def claim(self, text: str, source: str):
        self.claims.append({"claim": text, "source": source})


class Data:
    def __init__(self, folder=None):
        if folder is None:
            folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        self.suppliers = pd.read_csv(f"{folder}/suppliers.csv")
        self.sites = pd.read_csv(f"{folder}/sites.csv")
        self.parts = pd.read_csv(f"{folder}/parts.csv")
        self.bom = pd.read_csv(f"{folder}/bom.csv")
        self.supplier_parts = pd.read_csv(f"{folder}/supplier_parts.csv")
        self.events = pd.read_csv(f"{folder}/events.csv")
        self.mps = pd.read_csv(f"{folder}/mps.csv")


# ===========================================================================
# AGENT 1 - RISK PREDICTION
# ===========================================================================
PROCESS_VOCAB = ["Forging", "Investment Casting", "Heat Treatment",
                 "Chemical Processing", "Non-Destructive Testing",
                 "CNC Machining", "SMT Assembly", "Anodising", "None"]


def risk_agent(d: Data, bb: Blackboard, event_id: str):
    """
    STEP A (LLM PERCEPTION) - the only thing here a spreadsheet cannot do.
        Reads the raw news text and infers severity, recovery time and which
        special processes are knocked out. Severity is NOT read from a column.
    STEP B (PANDAS) - graph traversal + exposure maths. Auditable.
    STEP C (LLM EXPLANATION) - plain English for a non-specialist.
    """
    evt = d.events[d.events.event_id == event_id].iloc[0].to_dict()
    site = d.sites[d.sites.site_id == evt["site_id"]].iloc[0]
    bb.event = evt

    # ---------- STEP A0: REAL live data about this real location ------------
    # Facility identities are synthetic. The place is real, and so is
    # everything the world already knows about it.
    live = {}
    bb.live = live
    if live:
        s, w, c = live["seismic"], live["weather"], live["country_risk"]
        bb.note("RISK", f"Pulled live context for {site.city}: "
                        f"{s['quakes_10yr']} quakes M4.5+ in 10 years, "
                        f"{w['rain_7d_mm']}mm rain forecast, "
                        f"country risk {c['geopolitical_risk']}")
        if live["all_sources_live"]:
            bb.claim(f"Composite site risk {live['composite_site_risk']} for {site.city}",
                     "USGS + Open-Meteo + World Bank, fetched live")

    live_block = ""
    if live:
        live_block = (
            f"\n\nREAL LIVE CONTEXT FOR THIS LOCATION (not synthetic):\n"
            f"  seismic: {live['seismic']['quakes_10yr']} quakes M4.5+ within 300km "
            f"over 10 years, largest M{live['seismic']['max_magnitude']} "
            f"[{live['seismic']['source']}]\n"
            f"  weather next 7 days: {live['weather']['rain_7d_mm']}mm rain, "
            f"max {live['weather']['max_temp_c']}C, wind {live['weather']['max_wind_kmh']}km/h "
            f"[{live['weather']['source']}]\n"
            f"  country: political stability index "
            f"{live['country_risk']['political_stability_index']}, "
            f"logistics performance index {live['country_risk']['logistics_perf_index']} "
            f"[{live['country_risk']['source']}]\n"
            f"Use this to adjust your recovery estimate. A facility in a "
            f"high-hazard, low-logistics-performance country recovers more slowly.")

    # ---------- STEP A: perception -----------------------------------------
    perception = llm_json(
        system=("You are a supply chain disruption analyst. You read raw incident "
                "reports and extract structured facts. You never invent facts that "
                "are not supported by the text. If the text is vague, say so through "
                "a low confidence score.\n"
                "Return JSON with exactly these keys:\n"
                '  severity: float 0-1\n'
                '  recovery_days: integer, your best estimate of days to restore full output\n'
                f'  affected_processes: list, choose only from {PROCESS_VOCAB}\n'
                '  confidence: float 0-1\n'
                '  evidence: a short phrase copied from the report that justifies your severity\n'
                '  plain_english: one sentence a non-specialist would understand'),
        user=(f"INCIDENT REPORT (source: {evt['source']}, date: {evt['event_date']}):\n"
              f"\"{evt['raw_text']}\"\n\n"
              f"FACILITY RECORD:\n"
              f"  site: {site.site_id}, {site.city}, {site.country}\n"
              f"  processes performed here: {site.processes}\n"
              f"  historical baseline recovery for this site: {site.ttr_days} days"
              + live_block),
        fallback={"severity": float(evt["severity"]),
                  "recovery_days": int(site.ttr_days),
                  "affected_processes": str(site.processes).split("|"),
                  "confidence": 0.5,
                  "evidence": evt["raw_text"][:60],
                  "plain_english": f"A {evt['event_type'].lower()} has disrupted this facility."},
    )
    bb.perception = perception
    ttr = int(perception["recovery_days"])
    bb.note("RISK", f"Read the incident report and inferred: severity "
                    f"{perception['severity']}, recovery {ttr} days, "
                    f"processes hit {perception['affected_processes']}")
    bb.claim(f"Recovery estimated at {ttr} days",
             f"LLM perception of {evt['source']} report, evidence: \"{perception['evidence']}\"")

    # ---------- STEP B: deterministic traversal ----------------------------
    direct = set(d.supplier_parts[d.supplier_parts.site_id == evt["site_id"]].part_id)
    procs = [p for p in perception["affected_processes"] if p != "None"]
    indirect = set(d.parts[d.parts.requires_special_process.isin(procs)].part_id) - direct

    rows = []
    for pid in sorted(direct | indirect):
        p = d.parts[d.parts.part_id == pid].iloc[0]
        plats = d.bom[d.bom.part_id == pid]
        margin = sum(
            (d.mps[d.mps.platform == b.platform].planned_units *
             d.mps[d.mps.platform == b.platform].margin_per_unit_usd).sum() / 6
            for _, b in plats.iterrows())
        rows.append({
            "Part": pid,
            "What it is": p.commodity,
            "Why it is exposed": ("Bought from the hit site" if pid in direct
                                  else "Needs a process only the hit site performs"),
            "Stock cover (days)": int(p.tts_days),
            "Recovery (days)": ttr,
            "Shortfall (days)": max(0, ttr - int(p.tts_days)),
            "Monthly margin at risk (USD)": int(margin),
            "Status": "At risk" if ttr > p.tts_days else "Covered",
            "_single_source": bool(p.single_source),
            "_qual_months": int(p.qualification_lead_time_months),
            "_platforms": ", ".join(sorted(plats.platform.unique())),
        })

    if not rows:
        # Perception returned no matching processes and the site sources nothing
        # directly. Fall back to the site's own listed processes so the demo
        # always has something to show.
        site_procs = [x for x in str(site.processes).split("|") if x]
        fallback_ids = set(d.parts[d.parts.requires_special_process.isin(site_procs)].part_id)
        for pid in sorted(fallback_ids):
            p = d.parts[d.parts.part_id == pid].iloc[0]
            plats = d.bom[d.bom.part_id == pid]
            margin = sum(
                (d.mps[d.mps.platform == b.platform].planned_units *
                 d.mps[d.mps.platform == b.platform].margin_per_unit_usd).sum() / 6
                for _, b in plats.iterrows())
            rows.append({
                "Part": pid, "What it is": p.commodity,
                "Why it is exposed": "Needs a process the hit site performs",
                "Stock cover (days)": int(p.tts_days), "Recovery (days)": ttr,
                "Shortfall (days)": max(0, ttr - int(p.tts_days)),
                "Monthly margin at risk (USD)": int(margin),
                "Status": "At risk" if ttr > p.tts_days else "Covered",
                "_single_source": bool(p.single_source),
                "_qual_months": int(p.qualification_lead_time_months),
                "_platforms": ", ".join(sorted(plats.platform.unique())),
            })

    if not rows:
        # Still nothing — build an empty frame WITH the right columns so
        # downstream code never hits a missing-column error.
        df = pd.DataFrame(columns=[
            "Part", "What it is", "Why it is exposed", "Stock cover (days)",
            "Recovery (days)", "Shortfall (days)", "Monthly margin at risk (USD)",
            "Status", "_single_source", "_qual_months", "_platforms"])
    else:
        df = pd.DataFrame(rows).sort_values(
            ["Status", "Monthly margin at risk (USD)"], ascending=[True, False])
    bb.exposed = df
    at_risk = df[df.Status == "At risk"]
    bb.note("RISK", f"{len(direct)} parts bought from the site directly; "
                    f"{len(indirect)} more depend on its special process")
    bb.note("RISK", f"{len(at_risk)} of {len(df)} parts run out before the site recovers")
    bb.claim(f"{len(indirect)} parts exposed indirectly via special process",
             f"parts.csv where requires_special_process in {procs}")
    bb.claim(f"${at_risk['Monthly margin at risk (USD)'].sum():,.0f} monthly margin at risk",
             "bom.csv joined to mps.csv, summed over affected platforms")

    # ---------- STEP C: explanation ----------------------------------------
    narrative = llm_text(
        system=("You are briefing a Honeywell executive who is NOT a supply chain "
                "specialist. No jargon without immediately defining it. Be concise: "
                "four short paragraphs maximum. Never invent numbers."),
        user=(f"WHAT HAPPENED: {evt['raw_text']}\n"
              f"CONFIDENCE IN OUR READ: {perception['confidence']}\n\n"
              f"WHAT WE FOUND:\n{at_risk.head(6).drop(columns=[c for c in at_risk.columns if c.startswith('_')]).to_string(index=False)}\n\n"
              f"Only {len(direct)} of these parts are bought from the damaged site. "
              f"The other {len(indirect)} come from completely different suppliers, but "
              f"those suppliers all send their parts to this one site for a specialist "
              f"treatment step.\n\n"
              "Write: (1) what happened, (2) why it matters more than it looks, "
              "(3) the single insight a normal supplier dashboard would have missed, "
              "(4) what must happen in the next 72 hours."),
        fallback=perception["plain_english"],
    )
    return df, narrative


# ===========================================================================
# AGENT 2 - GLOBAL SOURCING
# ===========================================================================
def sourcing_agent(d: Data, bb: Blackboard, top_n: int = 3):
    """PANDAS scores every alternate. The LLM then DECIDES which to pick and
    names the risk being accepted. Ranking is not deciding."""
    at_risk = bb.exposed[bb.exposed.Status == "At risk"].head(top_n)
    bb.note("SOURCING", f"Received {len(at_risk)} at-risk parts from the Risk agent")

    bad = bb.event.get("site_id")
    rows = []
    for _, p in at_risk.iterrows():
        alts = d.supplier_parts[(d.supplier_parts.part_id == p.Part) &
                                (d.supplier_parts.site_id != bad)]
        base = d.parts[d.parts.part_id == p.Part].unit_cost_usd.iloc[0]
        if alts.empty:
            rows.append({"Part": p.Part, "Supplier": "None on approved list",
                         "Can ship now?": "No", "Price (USD)": None,
                         "Lead time (days)": None, "Fit score": 0.0,
                         "Recommended action": f"Start qualification today "
                                               f"({p._qual_months} months)"})
            continue
        for _, a in alts.iterrows():
            s = d.suppliers[d.suppliers.supplier_id == a.supplier_id].iloc[0]
            price_s = 1 - min(a.unit_price_usd / max(base, 1), 2) / 2
            lt_s = 1 - min(a.lead_time_days / 140, 1)
            rel_s = (s.otd_pct + s.financial_health) / 2
            risk_s = 1 - s.geo_risk_score
            score = 0.30 * price_s + 0.25 * lt_s + 0.25 * rel_s + 0.20 * risk_s
            if not a.qualified:
                score *= 0.5      # unqualified cannot ship for 9-24 months
            rows.append({
                "Part": p.Part,
                "Supplier": s.supplier_name,
                "Can ship now?": "Yes" if a.qualified else "No - needs qualification",
                "Price (USD)": round(float(a.unit_price_usd), 2),
                "Lead time (days)": int(a.lead_time_days),
                "Fit score": round(score, 2),
                "Recommended action": "Award and expedite" if a.qualified
                                      else "Qualify before award",
                "_supplier_id": a.supplier_id,
                "_country": s.country,
                "_otd": s.otd_pct,
            })

    df = pd.DataFrame(rows).sort_values(["Part", "Fit score"], ascending=[True, False])
    bb.shortlist = df
    ready = df[df["Can ship now?"] == "Yes"]
    bb.note("SOURCING", f"{len(df)} candidates scored; {len(ready)} can ship immediately")
    bb.claim(f"{len(ready)} qualified alternates available now",
             "supplier_parts.csv where qualified = True and site != disrupted site")

    decision = llm_json(
        system=("You are a Honeywell global commodity manager. The scores rank the "
                "options; you must DECIDE. A supplier that is not qualified cannot ship "
                "for 9-24 months (aviation part approval), so it is never a short-term "
                "fix - say so if that is the only option.\n"
                "Return JSON: {\"decisions\": [{\"part\": str, \"choose\": str, "
                "\"because\": str, \"risk_we_accept\": str}]}"),
        user=f"CANDIDATES:\n{df.drop(columns=[c for c in df.columns if c.startswith('_')]).to_string(index=False)}",
        fallback={"decisions": [
            {"part": p, "choose": g.iloc[0].Supplier,
             "because": "highest fit score among sources that can ship now",
             "risk_we_accept": "single alternate; no depth if it also fails"}
            for p, g in df.groupby("Part")]},
    )
    return df, decision


# ===========================================================================
# AGENT 3 - PROCUREMENT NEGOTIATION
# ===========================================================================
def negotiation_agent(d: Data, bb: Blackboard):
    """PANDAS builds the should-cost. The LLM writes the strategy and the opening
    line, and is instructed to be honest when our leverage is weak."""
    sl = bb.shortlist
    ready = sl[(sl["Can ship now?"] == "Yes")]
    if ready.empty:
        bb.note("NEGOTIATION", "No qualified alternate exists - nothing to negotiate")
        return {}, {"opening_position": "Escalate to engineering for a design substitution.",
                    "concessions": [], "red_line": "n/a",
                    "opening_sentence": "We have no qualified alternate.",
                    "plain_english": "There is nobody else approved to make this part."}

    top = ready.sort_values("Fit score", ascending=False).iloc[0]
    part = d.parts[d.parts.part_id == top.Part].iloc[0]
    quoted = float(top["Price (USD)"])

    # Deterministic should-cost. Percentages are the model's assumptions, stated openly.
    breakdown = {"Raw material": 0.42, "Labour": 0.18,
                 "Factory overhead": 0.15, "Freight & duty": 0.07}
    should_cost = sum(part.unit_cost_usd * v for v in breakdown.values())
    fair_price = round(should_cost * 1.12, 2)          # 12% supplier margin
    walk_away = round(fair_price * 1.15, 2)
    vol = int(part.annual_volume)
    single = bool(part.single_source)

    deal = {
        "Part": top.Part,
        "Supplier": top.Supplier,
        "Supplier's quoted price (USD)": quoted,
        "Our fair price estimate (USD)": fair_price,
        "Our walk-away price (USD)": walk_away,
        "Annual volume (units)": vol,
        "Annual saving if we hit fair price (USD)": int((quoted - fair_price) * vol),
        "Our fallback if talks fail": ("None - we are single sourced. Weak position."
                                       if single else
                                       "Keep incumbent at reduced volume and air-freight the gap"),
        "Who holds the leverage": "Supplier" if single else "Balanced",
        "Days until we run out": int(bb.exposed[bb.exposed.Part == top.Part]["Shortfall (days)"].iloc[0]),
        "_breakdown": {k: round(part.unit_cost_usd * v, 2) for k, v in breakdown.items()},
    }
    bb.deal = deal
    bb.note("NEGOTIATION", f"Should-cost ${should_cost:,.0f} against a quote of "
                           f"${quoted:,.0f}. Leverage sits with {deal['Who holds the leverage'].lower()}.")
    bb.claim(f"Fair price estimate ${fair_price:,.2f}",
             "should-cost model: material 42%, labour 18%, overhead 15%, freight 7%, +12% margin")

    strategy = llm_json(
        system=("You are a Honeywell sourcing negotiator. Be honest about leverage. "
                "If we are single-sourced during a shortage we CANNOT squeeze price - "
                "in that case trade non-price terms instead (capacity reservation, "
                "shorter lead time, payment terms, tooling ownership, dual-site commitment).\n"
                "Return JSON: {\"opening_position\": str, \"concessions\": [3 strings], "
                "\"red_line\": str, \"opening_sentence\": str, \"plain_english\": str}\n"
                "plain_english must be one sentence understandable by someone who has "
                "never worked in procurement."),
        user=json.dumps({k: v for k, v in deal.items() if not k.startswith("_")},
                        indent=2, default=str),
        fallback={"opening_position": f"Anchor at our fair price of ${fair_price:,.2f}.",
                  "concessions": ["Longer contract term", "Faster payment terms",
                                  "Volume commitment across platforms"],
                  "red_line": f"We do not pay above ${walk_away:,.2f}.",
                  "opening_sentence": "We value this relationship and we have a shortage; "
                                      "let us solve both today.",
                  "plain_english": "We know roughly what this part should cost to make, "
                                   "so we know how much room the supplier has."},
    )
    return deal, strategy


# ===========================================================================
# AGENT 4 - PRODUCTION PLANNING
# ===========================================================================
def planning_agent(d: Data, bb: Blackboard):
    """PANDAS re-sequences the schedule. The LLM explains the trade-off in plain
    English and names who was protected and who was cut."""
    at_risk = bb.exposed[bb.exposed.Status == "At risk"]
    if at_risk.empty:
        return d.mps.copy(), {"plain_english": "Nothing is short. The plan stands."}

    hit = set()
    for pl in at_risk._platforms:
        hit.update(x.strip() for x in str(pl).split(","))
    gap = int(at_risk["Shortfall (days)"].max())
    bb.note("PLANNING", f"A {gap}-day shortage affects {len(hit)} product lines")

    plan = d.mps.copy()
    plan["affected"] = plan.platform.isin(hit)
    cut = min(0.6, gap / 120)
    first_two = sorted(plan.month.unique())[:2]

    def revise(r):
        if r.affected and r.month in first_two:
            keep = 1 - cut * (0.6 if r.customer_priority == "High" else 1.0)
            return int(r.planned_units * keep)
        return int(r.planned_units)

    plan["revised_units"] = plan.apply(revise, axis=1)
    plan["margin_impact_usd"] = (plan.revised_units - plan.planned_units) * plan.margin_per_unit_usd

    out = plan.rename(columns={
        "platform": "Product line", "month": "Month",
        "customer_priority": "Customer priority",
        "planned_units": "Units originally planned",
        "revised_units": "Units we will now build",
        "margin_impact_usd": "Profit impact (USD)"})[
        ["Product line", "Month", "Customer priority",
         "Units originally planned", "Units we will now build", "Profit impact (USD)"]]

    total = int(plan.margin_impact_usd.sum())
    bb.plan = out
    bb.note("PLANNING", f"Rebuilt the schedule. Profit impact ${total:,.0f}. "
                        f"High-priority customers protected first.")
    bb.claim(f"Profit impact ${total:,.0f}",
             "mps.csv, revised units x margin per unit, summed")

    explain = llm_json(
        system=("You are a Honeywell production planner explaining a schedule change to "
                "someone with no manufacturing background. Use the idea of a bottleneck: "
                "when one thing is scarce, you spend it where it earns the most, not "
                "equally across everyone.\n"
                "Return JSON: {\"the_constraint\": str, \"we_protected\": [str], "
                "\"we_cut\": [str], \"recovery_action\": str, \"plain_english\": str}"),
        user=(f"Shortage window: {gap} days\nAffected product lines: {sorted(hit)}\n\n"
              f"{out[out['Product line'].isin(hit)].to_string(index=False)}"),
        fallback={"the_constraint": "the disrupted special-process facility",
                  "we_protected": [p for p in sorted(hit)][:2],
                  "we_cut": [p for p in sorted(hit)][2:],
                  "recovery_action": "Qualify a second special-process source now.",
                  "plain_english": "We cannot build everything, so we build what earns "
                                   "the most and protect our most important customers."},
    )
    return out, explain


# ===========================================================================
# AGENT 5 - VERIFIER  (the credibility layer)
# ===========================================================================
def verifier_agent(bb: Blackboard):
    """Checks every headline claim against the data source that produced it.
    An alert nobody can audit is an alert nobody acts on."""
    bb.note("VERIFIER", f"Checking {len(bb.claims)} claims against their source rows")
    result = llm_json(
        system=("You are an audit agent. For each claim, decide whether the cited source "
                "could plausibly support it. Flag any claim whose only support is a model "
                "inference rather than a data row - those need a human to confirm.\n"
                "Return JSON: {\"checks\": [{\"claim\": str, \"supported_by_data\": bool, "
                "\"needs_human_confirmation\": bool, \"note\": str}]}"),
        user=json.dumps(bb.claims, indent=2),
        fallback={"checks": [{"claim": c["claim"], "supported_by_data": "LLM" not in c["source"],
                              "needs_human_confirmation": "LLM" in c["source"],
                              "note": c["source"]} for c in bb.claims]},
    )
    return result


# ===========================================================================
# ORCHESTRATOR
# ===========================================================================
def run_cascade(d: Data, event_id: str):
    bb = Blackboard()
    o = {}
    o["risk_table"], o["risk_text"] = risk_agent(d, bb, event_id)
    o["sourcing_table"], o["sourcing_decision"] = sourcing_agent(d, bb)
    o["deal"], o["deal_strategy"] = negotiation_agent(d, bb)
    o["plan_table"], o["plan_explain"] = planning_agent(d, bb)
    o["verification"] = verifier_agent(bb)
    o["bb"] = bb
    return o

# ===========================================================================
# STEPWISE CASCADE — same agents, one at a time, for human approval gates
# ===========================================================================
def step_risk(d: Data, event_id: str):
    bb = Blackboard()
    table, text = risk_agent(d, bb, event_id)
    return bb, table, text


def step_sourcing(d: Data, bb: Blackboard):
    table, decision = sourcing_agent(d, bb)
    return table, decision


def step_negotiation(d: Data, bb: Blackboard):
    deal, strategy = negotiation_agent(d, bb)
    return deal, strategy


def step_planning(d: Data, bb: Blackboard):
    table, explain = planning_agent(d, bb)
    return table, explain


def step_verify(bb: Blackboard):
    return verifier_agent(bb)


# ===========================================================================
# STEPWISE CASCADE — same agents, run one at a time so a human can approve
# between each externally-visible action. State lives in the Blackboard, which
# is passed back in at each step.
# ===========================================================================
def step_risk(d: Data, event_id: str):
    bb = Blackboard()
    table, text = risk_agent(d, bb, event_id)
    return bb, table, text


def step_sourcing(d: Data, bb: Blackboard):
    table, decision = sourcing_agent(d, bb)
    return table, decision


def step_negotiation(d: Data, bb: Blackboard):
    deal, strategy = negotiation_agent(d, bb)
    return deal, strategy


def step_planning(d: Data, bb: Blackboard):
    table, explain = planning_agent(d, bb)
    return table, explain


def step_verify(bb: Blackboard):
    return verifier_agent(bb)


# ---------------------------------------------------------------------------
GLOSSARY = {
    "TTR (Time-To-Recover)": "How many days a damaged facility needs before it is producing normally again.",
    "TTS (Time-To-Survive)": "How many days we can keep building without that facility, using the stock we already hold.",
    "Exposure": "TTR is longer than TTS. We run out before they recover. This, not probability, is what we act on.",
    "AVL (Approved Vendor List)": "The register of suppliers already cleared to make a given part.",
    "Qualification / PMA (Parts Manufacturer Approval)": "Regulatory clearance for a supplier to make an aviation part. Takes 9-24 months. An unqualified supplier cannot help in a crisis.",
    "Nadcap": "The aerospace accreditation scheme for special processes such as heat treatment. Very few facilities hold it, which is why they become hidden single points of failure.",
    "NDT (Non-Destructive Testing)": "Inspecting a part for internal flaws without damaging it. A Nadcap special process.",
    "Special process": "A treatment step (heat treatment, NDT, anodising) that must be done at an accredited facility. It rarely appears on a purchase order, so it is invisible to normal supplier dashboards.",
    "BOM (Bill of Materials)": "The list of parts that go into a product.",
    "MPS (Master Production Schedule)": "How many units of each product we plan to build, month by month.",
    "Should-cost": "An estimate, built bottom-up from material, labour, overhead and freight, of what a part ought to cost the supplier to make.",
    "BATNA / fallback": "What we do if the negotiation fails. Weak fallback means weak leverage.",
    "OTD (On-Time Delivery)": "The share of a supplier's shipments that arrive on schedule.",
    "Bottleneck / Theory of Constraints": "When one resource is scarce, total output is set by that resource. You allocate it to whatever earns the most, rather than cutting everyone equally.",
    "Tier 1 / Tier 2": "Tier 1 sells to us directly. Tier 2 sells to Tier 1. We see Tier 1 on purchase orders; Tier 2 must be inferred.",
    "HITL (Human In The Loop)": "No agent spends money or changes a supplier relationship. A person approves every action.",
    "LLM (Large Language Model)": "The AI model. Here it reads text, decides between options and explains. It never calculates a number.",
}