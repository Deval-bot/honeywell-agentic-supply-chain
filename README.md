# Honeywell — Agentic Supply Chain Command Centre
### Capstone: Agentic AI for Business Transformation · 50 marks · Due 8 PM today

---

## 0. Setup in VS Code (10 minutes, do this first)

```powershell
# In VS Code terminal, inside the project folder
python -m venv .venv
.\.venv\Scripts\activate
pip install streamlit pandas numpy requests

python generate_data.py          # writes 7 CSVs into .\data\
streamlit run app.py             # opens http://localhost:8501
```

To turn on the LLM reasoning layer:
```powershell
$env:ANTHROPIC_API_KEY="sk-ant-..."
streamlit run app.py
```
If no key is set, the app runs in **MOCK MODE**: every number is still computed
live, only the narrative text is stubbed. **The demo cannot fail on stage.**
That is a deliberate design choice — say so in the video.

Deploy for the "Application link" deliverable: push to GitHub, then
share.streamlit.io → New app → point at `app.py`. Takes ~5 minutes.
Add `ANTHROPIC_API_KEY` under App settings → Secrets.

---

## 1. Timeline to 8 PM (assume you start ~9 AM)

| Time | Owner | Task | Gate |
|---|---|---|---|
| 09:00–09:30 | All 5 | Read this file. Agree the cascade story. Assign roles. | Everyone can say the one-line pitch |
| 09:30–10:30 | Dev 1 | `python generate_data.py`, sanity-check CSVs, tweak row counts | Data tab renders |
| 09:30–11:30 | Dev 2 | Get `app.py` running locally, fix any Windows path issues | Cascade button works in mock mode |
| 10:30–12:30 | Dev 1 | Wire the real API key, tune the 4 system prompts | Narratives read like a consultant, not a chatbot |
| 10:30–13:00 | Member 3 | Build the PPT (outline in §4) | 10 slides, no walls of text |
| 13:00–14:00 | All | **HARD FREEZE on code.** Whatever works, works. | Screen-record a clean cascade run |
| 14:00–15:00 | Member 4 | Deploy to Streamlit Cloud, get the public link | Link opens on someone else's laptop |
| 14:00–15:30 | All | Rehearse the video once, with the script in §5 | Under 10:00 on the timer |
| 15:30–17:00 | All | Record. One take per person if possible. | Faces on, everyone speaks |
| 17:00–18:30 | Member 5 | Edit, export, upload | File plays start to finish |
| 18:30–19:30 | Deval | Final check: video + Streamlit link + PPT all submitted | — |
| 19:30–20:00 | — | Buffer. Something will break. | — |

**The long pole is the video, not the code.** Five people, faces on, under
10 minutes, everyone speaking at least once. Start recording at 15:30 whether
or not the app is perfect.

---

## 2. Role split (5 members)

1. **Data & Risk Agent** — owns `generate_data.py` + `risk_prediction_agent`
2. **Sourcing & Negotiation Agents** — owns agents 2 and 3, tunes prompts
3. **Planning Agent & UI** — owns agent 4 + `app.py` layout
4. **Deployment & Demo** — Streamlit Cloud, screen recording, backup video
5. **Narrative** — PPT, problem-statement justification, video edit

Everyone must be able to explain the *cascade*. Marks are lost when one person
clearly does not know what the others built.

---

## 3. The 5-mark problem statement — how to justify **agentic**, not just AI

Do not say "we used AI to analyse supply chain data." Say this:

> Honeywell's exposure does not live with the supplier that invoices it. It lives
> with the physical facility that performs the accredited special process. Two
> independent-looking Tier-1 suppliers routinely converge on the same Nadcap
> heat-treat house. That convergence never appears on a purchase order, so it is
> invisible to the ERP vendor master and to every supplier-level dashboard.
>
> Finding it requires **multi-hop traversal over an inferred graph**, using
> unstructured evidence (news, dockets, customs data) that arrives in the wrong
> language at the wrong time. Then it requires a **sequence of dependent decisions**
> — re-source, re-price, re-plan — where each step's output is the next step's input.
>
> A dashboard cannot do this. A single prompt cannot do this. It needs agents that
> hold goals, call tools, pass state to one another, and stop for a human before
> spending money.

**Why exactly four agents:** each owns one decision, and each hands its output to
the next. Risk decides *what is exposed*. Sourcing decides *who can supply*.
Negotiation decides *at what price and terms*. Planning decides *what we still build*.

Ground it in a real framework — **Simchi-Levi's Risk Exposure Index** (HBR, 2014,
developed with Ford). Exposure exists wherever **Time-To-Recover > Time-To-Survive**.
The insight: stop trying to predict the probability of a fire. Find the nodes where
you have no slack. Ford's result was that the highest-exposure nodes were cheap
commodity parts, not expensive castings. Cost has nothing to do with exposure.

Citing a peer-reviewed framework is worth a mark on its own. Most groups will invent
a scoring model.

---

## 4. PPT outline (10 slides)

1. **Title** — Honeywell · Agentic Supply Chain Command Centre · 5 names
2. **The company in one slide** — $37.4B sales 2025, 4 segments, Aerospace $17.5B, backlog $37.5B, splitting into 3 companies by Q3 2026
3. **The problem** — your problem statement, plus the evidence: management named "mechanical supply chain headwinds in aerospace" and "inventory headwinds" in Q1 2026. Inventory up, output constrained = classic unbuffered bottleneck
4. **Why the separation makes it worse** — one Integrated Supply Chain buying for $37B becomes three buying separately. Visibility must be rebuilt in software because the org chart is destroying it
5. **The hidden convergence** — the diagram: platform → 2 independent Tier-1s → 1 heat-treat house. "Dual sourcing at Tier 1 does not survive convergence at Tier 2."
6. **Why agentic, not a dashboard** — multi-hop inference + dependent decision sequence + unstructured evidence
7. **Architecture** — the 4-agent cascade, the blackboard, the human approval gate. Say: *deterministic core + LLM reasoning layer*. The core does the maths and cannot hallucinate; the LLM does the judgement and cites its evidence
8. **Synthetic data** — 30 suppliers, 43 sites, 60 parts, 4 platforms, 98 sourcing edges, 21 events. Show the schema. Explain that we model **sites and processes as first-class nodes**, which is the whole trick
9. **Demo screenshots** — the metrics row, the handoff log, one agent's reasoning
10. **Impact & what we'd do next** — metrics we'd measure (hours from event to alert, alert precision, % spend with Tier-2 mapped, single-source parts with a pre-qualified alternate). Next: real entity resolution, Neo4j, human feedback loop

---

## 5. Video script (10:00 hard cap)

| Time | Speaker | Content |
|---|---|---|
| 0:00–1:00 | M1 | Company + problem statement. Land the sentence: *"Honeywell's exposure doesn't live with the supplier that invoices it."* |
| 1:00–2:00 | M1 | Why agentic. Multi-hop, dependent decisions, unstructured evidence. |
| 2:00–3:00 | M2 | Data model. Sites and processes as first-class nodes. Show the schema slide. |
| 3:00–4:30 | M2 | **Live demo part 1.** Trigger EVT-021 (the fire). Risk agent runs. Point at: only 2 parts sourced directly, 21 more exposed via special process. |
| 4:30–5:30 | M3 | Sourcing agent. Explain the qualified/unqualified split — *"an unqualified supplier is not a short-term fix, PMA takes 9 to 24 months."* |
| 5:30–6:30 | M4 | Negotiation agent. Should-cost breakdown, target vs walk-away, and the honest BATNA line: *"single source, weak position — so we trade non-price terms."* |
| 6:30–7:30 | M5 | Planning agent. Theory of Constraints framing: throughput per constrained unit, not equal-pain cuts. |
| 7:30–8:30 | M5 | Show the handoff log. **This is the money shot.** Four agents, one trigger, state passing between them. |
| 8:30–9:30 | M1 | Limitations, honestly: synthetic data, no real entity resolution, human approves every action. Then metrics and next steps. |
| 9:30–10:00 | All | Close. |

**Rehearse once with a timer.** You will run 40% over on the first pass.

---

## 6. If you have spare time (in priority order)

1. Tune the four system prompts in `agents.py`. This is the single highest-ROI hour — it is what makes the output read like a commodity manager and not like a chatbot.
2. Add a **verifier agent** that checks each claim against its source row and prints a citation trail. Say out loud: *"the alert nobody can audit is the alert nobody acts on."* This is the thing graders remember.
3. Add a simple network chart of the convergence using `st.graphviz_chart`.
4. Add a human approval button before the Negotiation agent fires — reinforces the HITL story.

**Do not** add: authentication, a database, more agents, prettier CSS. None of it is marked.

---

## 7. Honest limitations (put these on a slide — it wins marks, it doesn't lose them)

- Synthetic data. Real Tier-2 discovery needs customs/bill-of-lading feeds, and those miss domestic shipments entirely.
- No real entity resolution. Mapping "PCC Structurals Inc" and "PRECISION CASTPARTS — OGDEN" to one physical site is the hardest step and we stubbed it.
- TTR is estimated, not observed.
- Every action is human-approved. Nothing here spends money autonomously — and in a regulated aerospace supply chain, nothing should.

Naming what you did *not* solve is the clearest signal that you understood the problem.
