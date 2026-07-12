"""
Honeywell Agentic Supply Chain Command Centre
Run:  streamlit run app.py
"""
import os
import streamlit as st

st.set_page_config(page_title="Honeywell Agentic Supply Chain",
                   page_icon="⚙", layout="wide")

# Streamlit Cloud stores secrets in st.secrets, not env vars.
# This MUST run before agents.py is imported, because agents.py checks for the
# key at import time to decide whether to run in mock mode.
try:
    if "ANTHROPIC_API_KEY" in st.secrets:
        os.environ["ANTHROPIC_API_KEY"] = st.secrets["ANTHROPIC_API_KEY"]
except Exception:                                            # noqa: BLE001
    pass

import pandas as pd                                          # noqa: E402
from agents import Data, GLOSSARY, mock_mode    # noqa: E402


@st.cache_resource
def load():
    return Data()


d = load()


def clean(df):
    """Hide internal columns (prefixed with _) from the user."""
    return df[[c for c in df.columns if not str(c).startswith("_")]]


def glossary_footer():
    st.divider()
    with st.expander("Terms and abbreviations used on this page"):
        for k, v in GLOSSARY.items():
            st.markdown(f"**{k}** — {v}")


# ===========================================================================
st.title("Honeywell — Agentic Supply Chain Command Centre")
st.caption("Five agents. One disruption. Each agent hands its answer to the next. "
           "A person approves every action.")

with st.expander("How this works, in ninety seconds", expanded=False):
    st.markdown("""
Honeywell buys parts from thousands of suppliers. When something goes wrong at one
factory, the hard question is not *"is that factory important?"* — it is
**"what else breaks, that nobody expected to break?"**

The answer is usually hidden. Two suppliers who look completely independent often
send their parts to the **same** specialist treatment facility — a heat-treatment
house, say. That facility never appears on a purchase order, so no ordinary
dashboard can see it. Buying from two suppliers feels safe. It isn't.

Finding that requires reading news reports, walking a supply network several steps
deep, and then making four decisions in sequence, where each answer changes the next.
That is what these agents do:

| | Agent | The question it answers |
|---|---|---|
| 1 | **Risk** | What breaks, and how long until we run out? |
| 2 | **Sourcing** | Who else can make this, and can they actually ship? |
| 3 | **Negotiation** | What is a fair price, and how much power do we really have? |
| 4 | **Planning** | We cannot build everything — so what do we build? |
| 5 | **Verifier** | Can every number above be traced back to a source? |

**The design rule:** the AI model never calculates a number. It *reads* messy text,
it *chooses* between options, and it *explains*. All arithmetic happens in code you
can audit line by line.
""")

if mock_mode():
    st.warning("**Demo mode** — no API key found. Every number below is computed live "
               "and is real. Only the AI reasoning text is stubbed. The demo cannot fail.")

# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Step 1 — pick a disruption")
    ev = d.events.sort_values("severity", ascending=False)
    labels = [f"{r.event_id} · {r.event_type}" for _, r in ev.iterrows()]
    pick = st.selectbox("Incoming incident report", labels, index=0)
    event_id = pick.split(" ")[0]
    row = d.events[d.events.event_id == event_id].iloc[0]

    st.markdown(f"**Reported by:** {row.source}  \n**Facility:** {row.site_id}, {row.country}")
    st.info(f"_{row.raw_text}_")
    st.caption("This is unstructured text. No severity score, no recovery estimate. "
               "The Risk agent has to read it and work those out.")

    st.header("Step 2 — run the agents")
    st.caption("Each agent stops for your approval before the next one acts on its output. "
               "You can approve, or override the decision.")
    start = st.button("Start — run Risk agent", type="primary", use_container_width=True)
    if st.button("Reset", use_container_width=True):
        for k in ["stage", "bb", "risk_tbl", "risk_txt", "src_tbl", "src_dec",
                  "deal", "deal_strat", "plan_tbl", "plan_exp", "verify",
                  "approved_supplier", "approved_mandate", "approved_plan"]:
            st.session_state.pop(k, None)
        st.rerun()

# ---------------------------------------------------------------------------
from agents import (step_risk, step_sourcing, step_negotiation,   # noqa: E402
                    step_planning, step_verify)

# stage tracks how far the human has approved the cascade
if start:
    with st.spinner("Risk agent reading the incident report and walking the network…"):
        bb, rt, rx = step_risk(d, event_id)
    st.session_state.update(stage="risk_done", bb=bb, risk_tbl=rt, risk_txt=rx)
    for k in ["src_tbl", "deal", "plan_tbl", "verify", "approved_supplier",
              "approved_mandate", "approved_plan"]:
        st.session_state.pop(k, None)

stage = st.session_state.get("stage")

tabs = st.tabs(["Overview", "1 · Risk", "2 · Sourcing", "3 · Negotiation",
                "4 · Planning", "5 · Verifier", "Live signals", "The data"])

# ---------------------------------------------------------------------------
# OVERVIEW
# ---------------------------------------------------------------------------
with tabs[0]:
    if not stage:
        st.info("Pick an incident in the sidebar, then press **Start — run Risk agent**. "
                "Each agent will pause for your approval before the next one acts.")
    else:
        bb = st.session_state.bb
        risk = st.session_state.risk_tbl
        at_risk = risk[risk.Status == "At risk"]
        direct = int((risk["Why it is exposed"] == "Bought from the hit site").sum())
        indirect = len(risk) - direct

        steps = ["risk_done", "sourcing_done", "negotiation_done", "planning_done", "verify_done"]
        names = ["Risk", "Sourcing", "Negotiation", "Planning", "Verifier"]
        done = steps.index(stage) + 1 if stage in steps else 1
        st.progress(done / 5, text=f"Human-approved through: {names[done-1]} "
                                   f"({done} of 5 agents)")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Parts that will run short", f"{len(at_risk)}")
        c2.metric("Monthly profit at risk",
                  f"${at_risk['Monthly margin at risk (USD)'].sum()/1e6:,.1f}M")
        if st.session_state.get("src_tbl") is not None:
            c3.metric("Suppliers who can ship now",
                      int((st.session_state.src_tbl["Can ship now?"] == "Yes").sum()))
        if st.session_state.get("plan_tbl") is not None:
            c4.metric("Profit impact of the re-plan",
                      f"${st.session_state.plan_tbl['Profit impact (USD)'].sum()/1e6:,.1f}M")

        st.subheader("The finding")
        st.success(f"**Only {direct} part(s) are bought from the damaged facility. "
                   f"Another {indirect} break anyway** — they come from different suppliers, "
                   f"but every one of those suppliers sends parts to this same facility for "
                   f"a specialist treatment step. Buying from two suppliers did not protect us, "
                   f"because both roads lead to the same bridge.")

        st.subheader("What the agents said to each other")
        st.caption("Each line is one agent finishing its work and passing the result on. "
                   "Between each externally-visible step, a human approved.")
        for line in bb.log:
            agent, msg = line.split(" | ", 1)
            st.markdown(f"`{agent}` &nbsp; {msg}", unsafe_allow_html=True)
    glossary_footer()

# ---------------------------------------------------------------------------
# 1 RISK  — gate: approve the interpretation
# ---------------------------------------------------------------------------
with tabs[1]:
    st.subheader("Risk agent")
    st.caption("Reads the incident report. Works out how bad it is and how long recovery "
               "will take. Then walks the supply network to find everything that breaks. "
               "This step only reads data, so it runs freely — but you approve its "
               "interpretation before it drives any sourcing decision.")
    if not stage:
        st.info("Press **Start — run Risk agent** in the sidebar.")
    else:
        bb = st.session_state.bb
        p = bb.perception
        st.markdown("##### What the model read out of the news report")
        st.caption("A spreadsheet cannot do this step. The report is prose; these are facts.")
        a, b = st.columns(2)
        a.metric("How bad, 0 to 1", p["severity"])
        b.metric("Days until they recover", p["recovery_days"])
        st.markdown(f"**Processes knocked out:** {', '.join(p['affected_processes'])}")
        st.markdown(f"**Evidence it based this on:** _\u201c{p['evidence']}\u201d_")

        st.markdown("##### What breaks as a result")
        st.caption("Exposed means: our stock runs out before the facility comes back. "
                   "We are not predicting the chance of a fire — we are finding where "
                   "we have no cushion.")
        st.dataframe(clean(st.session_state.risk_tbl), use_container_width=True, hide_index=True)

        st.markdown("##### Briefing")
        st.markdown(st.session_state.risk_txt)

        # ---- HUMAN GATE 1 ----
        st.divider()
        with st.container(border=True):
            st.markdown("### \U0001F464 Human approval — do we accept this reading?")
            st.caption("If you disagree with the recovery estimate, override it. "
                       "Everything downstream uses the number you approve.")
            col1, col2 = st.columns([2, 1])
            override = col1.number_input("Recovery days (override if needed)",
                                         min_value=1, max_value=365,
                                         value=int(p["recovery_days"]))
            if col2.button("Approve & run Sourcing agent", type="primary"):
                if override != int(p["recovery_days"]):
                    # human overrides the LLM's recovery estimate; recompute exposure
                    rt = st.session_state.risk_tbl.copy()
                    rt["Recovery (days)"] = override
                    rt["Shortfall (days)"] = (override - rt["Stock cover (days)"]).clip(lower=0)
                    rt["Status"] = ["At risk" if override > s else "Covered"
                                    for s in rt["Stock cover (days)"]]
                    st.session_state.risk_tbl = rt
                    bb.exposed = rt
                    bb.note("HUMAN", f"Overrode recovery estimate to {override} days")
                else:
                    bb.note("HUMAN", "Approved the risk interpretation")
                with st.spinner("Sourcing agent finding qualified alternates…"):
                    tbl, dec = step_sourcing(d, bb)
                st.session_state.update(stage="sourcing_done", src_tbl=tbl, src_dec=dec)
                st.rerun()
    glossary_footer()

# ---------------------------------------------------------------------------
# 2 SOURCING  — gate: approve or override the supplier
# ---------------------------------------------------------------------------
with tabs[2]:
    st.subheader("Sourcing agent")
    st.caption("Finds who else could make these parts. The critical distinction: a supplier "
               "who is already approved can ship next week. One who is not approved needs "
               "9 to 24 months of regulatory clearance — useless in a crisis. Choosing a "
               "supplier commits money and a relationship, so a human approves it.")
    if st.session_state.get("src_tbl") is None:
        st.info("Approve the Risk step first.")
    else:
        st.dataframe(clean(st.session_state.src_tbl), use_container_width=True, hide_index=True)
        st.caption("Fit score weighs price 30%, lead time 25%, reliability 25%, country risk 20%. "
                   "Any supplier who is not yet approved has their score halved.")

        st.markdown("##### The agent's recommendation")
        st.caption("The score ranks the options. It does not decide. Deciding means naming "
                   "the risk you are choosing to accept.")
        for dec in st.session_state.src_dec.get("decisions", []):
            with st.container(border=True):
                st.markdown(f"**{dec.get('part','')} \u2192 {dec.get('choose','')}**")
                st.markdown(f"Why: {dec.get('because','')}")
                st.markdown(f"\u26a0 Risk we accept: {dec.get('risk_we_accept','')}")

        # ---- HUMAN GATE 2 ----
        st.divider()
        with st.container(border=True):
            st.markdown("### \U0001F464 Human approval — which supplier do we pursue?")
            ready = st.session_state.src_tbl[
                st.session_state.src_tbl["Can ship now?"] == "Yes"]
            if ready.empty:
                st.error("No approved alternate can ship now. Approving will send this to "
                         "engineering for a design substitution instead.")
                choices = ["Escalate to engineering"]
            else:
                choices = [f"{r.Part} \u2192 {r.Supplier} (${r['Price (USD)']:,.0f}, "
                           f"fit {r['Fit score']})" for _, r in ready.iterrows()]
            col1, col2 = st.columns([2, 1])
            pick = col1.selectbox("Supplier to authorise", choices)
            if col2.button("Approve & run Negotiation agent", type="primary"):
                st.session_state.bb.note("HUMAN", f"Authorised sourcing: {pick}")
                with st.spinner("Negotiation agent building the should-cost model…"):
                    deal, strat = step_negotiation(d, st.session_state.bb)
                st.session_state.update(stage="negotiation_done", deal=deal, deal_strat=strat)
                st.rerun()
    glossary_footer()

# ---------------------------------------------------------------------------
# 3 NEGOTIATION  — gate: approve the negotiating mandate
# ---------------------------------------------------------------------------
with tabs[3]:
    st.subheader("Negotiation agent")
    st.caption("Estimates what the part should cost the supplier to make, from the bottom up. "
               "That tells us how much room there is in their price. The walk-away price is a "
               "mandate to a counterparty, so a human signs it off before it is used.")
    if st.session_state.get("deal") is None:
        st.info("Approve the Sourcing step first.")
    elif not st.session_state.deal:
        st.error("No approved alternate supplier exists. There is nothing to negotiate. "
                 "This must go to engineering for a design change.")
    else:
        deal, strat = st.session_state.deal, st.session_state.deal_strat
        quoted = deal["Supplier's quoted price (USD)"]
        fair = deal["Our fair price estimate (USD)"]
        walk = deal["Our walk-away price (USD)"]
        a, b, c = st.columns(3)
        a.metric("They quoted", f"${quoted:,.2f}")
        b.metric("We think it's worth", f"${fair:,.2f}")
        c.metric("We walk away above", f"${walk:,.2f}")

        st.markdown("##### What the part should cost to make")
        st.bar_chart(pd.Series(deal["_breakdown"]), horizontal=True)
        st.caption("Assumptions: raw material 42%, labour 18%, factory overhead 15%, "
                   "freight and duty 7%, plus a 12% supplier margin.")

        st.markdown("##### Our honest position")
        st.markdown(f"- **Who holds the power:** {deal['Who holds the leverage']}")
        st.markdown(f"- **If talks fail, we:** {deal['Our fallback if talks fail']}")
        st.markdown(f"- **Days until we run out:** {deal['Days until we run out']}")

        st.markdown("##### The plan")
        with st.container(border=True):
            st.markdown(f"**Open with:** _\u201c{strat.get('opening_sentence','')}\u201d_")
            st.markdown(f"**Opening position:** {strat.get('opening_position','')}")
            st.markdown("**Things we can give away cheaply:**")
            for c_ in strat.get("concessions", []):
                st.markdown(f"- {c_}")
            st.markdown(f"**Red line:** {strat.get('red_line','')}")
        st.info(f"**In plain English:** {strat.get('plain_english','')}")

        # ---- HUMAN GATE 3 ----
        st.divider()
        with st.container(border=True):
            st.markdown("### \U0001F464 Human approval — do we authorise this mandate?")
            st.caption("Set the maximum price the negotiator is allowed to accept. "
                       "This is the number that becomes an offer to the supplier.")
            col1, col2 = st.columns([2, 1])
            mandate = col1.number_input("Authorised walk-away price (USD)",
                                        min_value=0.0, value=float(walk), step=10.0)
            if col2.button("Approve & run Planning agent", type="primary"):
                st.session_state.bb.note(
                    "HUMAN", f"Authorised negotiating mandate up to ${mandate:,.0f}")
                with st.spinner("Planning agent re-sequencing the schedule…"):
                    tbl, exp = step_planning(d, st.session_state.bb)
                st.session_state.update(stage="planning_done", plan_tbl=tbl, plan_exp=exp)
                st.rerun()
    glossary_footer()

# ---------------------------------------------------------------------------
# 4 PLANNING  — gate: approve the revised schedule
# ---------------------------------------------------------------------------
with tabs[4]:
    st.subheader("Planning agent")
    st.caption("We cannot build everything. When one input is scarce, you spend it where it "
               "earns the most — you do not cut every product line equally. Changing the "
               "factory schedule affects customer commitments, so a human approves it.")
    if st.session_state.get("plan_tbl") is None:
        st.info("Approve the Negotiation step first.")
    else:
        ex = st.session_state.plan_exp
        st.info(f"**In plain English:** {ex.get('plain_english','')}")
        a, b = st.columns(2)
        a.markdown("**We protected**")
        for x in ex.get("we_protected", []):
            a.markdown(f"- {x}")
        b.markdown("**We cut**")
        for x in ex.get("we_cut", []) or ["\u2014 nothing"]:
            b.markdown(f"- {x}")
        st.markdown(f"**The bottleneck:** {ex.get('the_constraint','')}")
        st.markdown(f"**Recovery action:** {ex.get('recovery_action','')}")

        st.markdown("##### The revised build schedule")
        st.dataframe(st.session_state.plan_tbl, use_container_width=True, hide_index=True)

        # ---- HUMAN GATE 4 ----
        st.divider()
        with st.container(border=True):
            st.markdown("### \U0001F464 Human approval — do we commit this schedule?")
            st.caption("Committing changes what the factory builds next month and which "
                       "customer orders slip. The final agent then audits every number.")
            if st.button("Approve & run Verifier agent", type="primary"):
                st.session_state.bb.note("HUMAN", "Committed the revised production schedule")
                with st.spinner("Verifier auditing every claim against its source…"):
                    v = step_verify(st.session_state.bb)
                st.session_state.update(stage="verify_done", verify=v)
                st.rerun()
    glossary_footer()

# ---------------------------------------------------------------------------
# 5 VERIFIER
# ---------------------------------------------------------------------------
with tabs[5]:
    st.subheader("Verifier agent")
    st.caption("An alert nobody can audit is an alert nobody acts on. This agent traces every "
               "headline number back to the row that produced it, and flags anything that rests "
               "on the model's judgement rather than on data.")
    if st.session_state.get("verify") is None:
        st.info("Approve the Planning step first.")
    else:
        for chk in st.session_state.verify.get("checks", []):
            ok = chk.get("supported_by_data")
            human = chk.get("needs_human_confirmation")
            icon = "\u2705" if ok else ("\U0001F7E1" if human else "\u274c")
            with st.container(border=True):
                st.markdown(f"{icon} **{chk.get('claim','')}**")
                st.caption(f"Traced to: {chk.get('note','')}")
                if human:
                    st.caption("This rests on the model reading a document. A human should confirm it.")
        st.success("Cascade complete. Five agents ran; a human approved every "
                   "externally-visible action along the way.")
    glossary_footer()


# ---------------------------------------------------------------------------
# LIVE SIGNALS  (real, open, key-free)
# ---------------------------------------------------------------------------
with tabs[6]:
    st.subheader("Live signals")
    st.caption("The supply network is synthetic — no manufacturer publishes its bill of "
               "materials, prices or inventory. But the facilities sit in real cities, and "
               "everything the world already knows about those places is real and fetched live.")

    src = pd.DataFrame([
        ["Seismic hazard", "USGS Earthquake Catalog", "Real, live", "Risk agent"],
        ["Weather impacts", "Open-Meteo", "Real, live", "Risk agent"],
        ["Geopolitical exposure", "World Bank governance indicators", "Real, live", "Risk + Sourcing"],
        ["Logistics bottlenecks", "World Bank logistics performance index", "Real, live", "Risk + Sourcing"],
        ["Supplier failure signals", "GDELT global news feed", "Real, live", "Risk agent"],
        ["Company financials", "Honeywell FY2025 10-K", "Real, filed", "Planning agent"],
        ["Prices, capacity, bill of materials", "—", "Synthetic, disclosed", "All agents"],
        ["Tariff changes", "—", "Synthetic, disclosed", "Sourcing agent"],
    ], columns=["Signal", "Source", "Status", "Used by"])
    st.dataframe(src, use_container_width=True, hide_index=True)

    st.markdown("##### Pull live context for any facility")
    city = st.selectbox("City", sorted(d.sites.city.unique()))
    country = d.sites[d.sites.city == city].country.iloc[0]

    if st.button("Fetch live data now"):
        with st.spinner("Calling USGS, Open-Meteo and the World Bank…"):
            from live_data import enrich_site, news_signals
            live = enrich_site(city, country)
            news = news_signals(f"{city} factory OR plant OR manufacturing")

        if live["all_sources_live"]:
            st.success("All three feeds returned live data.")
        else:
            st.warning("One or more feeds fell back to a cached value. "
                       "The app keeps running — that is the point of failing soft.")

        a, b, c, e = st.columns(4)
        a.metric("Quakes M4.5+, 10 yrs", live["seismic"]["quakes_10yr"])
        b.metric("Rain forecast, 7 days", f"{live['weather']['rain_7d_mm']} mm")
        c.metric("Country risk, 0–1", live["country_risk"]["geopolitical_risk"])
        e.metric("Composite site risk", live["composite_site_risk"])

        st.caption(f"Seismic: {live['seismic']['source']} · "
                   f"Weather: {live['weather']['source']} · "
                   f"Country: {live['country_risk']['source']}")

        st.markdown("##### Real news headlines the Risk agent would read")
        st.caption("This is the unstructured text the perception step turns into "
                   "severity, recovery days and affected processes.")
        for a_ in news[:5]:
            if a_["url"]:
                st.markdown(f"- [{a_['title']}]({a_['url']}) — _{a_['domain']}_")
            else:
                st.markdown(f"- {a_['title']}")

    st.markdown("##### Honeywell, from the filings")
    from live_data import HONEYWELL_FACTS as HF
    f1, f2, f3 = st.columns(3)
    f1.metric("FY2025 sales", f"${HF['fy2025_sales_usd_bn']}B")
    f2.metric("Aerospace sales", f"${HF['aerospace_sales_usd_bn']}B")
    f3.metric("Backlog", f"${HF['backlog_usd_bn']}B")
    st.caption(f"Source: {HF['source']}")
    glossary_footer()

# ---------------------------------------------------------------------------
# DATA
# ---------------------------------------------------------------------------
with tabs[7]:
    st.subheader("The supply network")
    st.caption("30 suppliers · 43 facilities · 60 parts · 4 product lines · "
               "98 supply links · 21 incident reports")
    st.markdown("""
**The one modelling choice that makes this work:** we treat **facilities** and
**treatment processes** as things in their own right, not just suppliers.

Risk does not sit with the company that sends you the invoice. It sits with the
physical building that performs the accredited treatment step. Two suppliers who
look independent on paper can share that building. That shared dependency never
appears in a purchase order, and so it never appears in an ordinary supplier database.
""")
    which = st.radio("Table", ["events", "parts", "sites", "suppliers",
                               "supplier_parts", "bom", "mps"], horizontal=True)
    st.dataframe(getattr(d, which), use_container_width=True, hide_index=True)
    glossary_footer()