## Kiosk KAI: AUTOGMAP's live data, and the Kiosk Application Form and TARA beside it

The `kiosk-kai` MCP server (https://indev.eko.in/kiosk-kai/mcp, key from the KAI_KEY environment variable) answers
from the live databases and the code of AUTOGMAP, the Kiosk Application Form (where AUTOGMAP's leads apply) and TARA
(which runs the CSPs those applicants become). It is read-only, and no tool returns a person's name, phone, email or
message. Never print KAI_KEY or write it into a file.

When to use it in this repository:
- Before changing campaigns, journeys, qualification, branch matching or the goal: check the live figures first with
  `autogmap.goals`, `autogmap.lead_pipeline`, `autogmap.campaigns` and `autogmap.discovery`.
- For anything that crosses into the form or TARA (did people we messaged apply? does TARA have CSPs where our
  leads are?): start with `autogmap.acquisition_funnel(days, state)` or `autogmap.acquisition_place(state, district)`.
  Their `across` section already joins the three systems.
- For the TARA figures our growth agent's goal is set from (`scripts/export_business_context.py` copies them into
  `data/business_context.json`): `autogmap.tara_context(states)` gives them live, in the same keys
  (`csp_network`, `revenue_forecasts`). Use it to check whether `business_context.json` is stale (its `exported_at`
  should be today's 04:30 IST run). The export failed from 17 October 2026; it ran again on 29 October and matched
  TARA live.
- For the form's or TARA's code: `core.search_code(system="ekokiosk" or "tara", query)`, then `core.read_code`. For
  AUTOGMAP's own code, this repository is the truth; Kiosk KAI's copy (`system="autogmap"`) is a snapshot that can
  lag. `core.impact(system, target)` lists what depends on a file, table or job.
- The app itself reads Kiosk KAI too (`src/services/kiosk_kai.py`): the growth plan's "After AutoGMap" part
  (`growth_plan.beyond`: `autogmap.acquisition_funnel`, `ekokiosk.campaign_targets`) and TARA live in the goal
  (`business_context.with_live_tara`: `autogmap.tara_context`). It signs in with the app's own key,
  `KIOSK_KAI_APP_KEY`, never a person's KAI_KEY; without it those parts are off and the plan works as before.
- To ask in plain words: `core.ask(question)`. It costs money and the team shares USD 5 a day, so ask the user first.

How to answer with it:
- Name the system (AUTOGMAP, Kiosk Application Form, TARA) and the `as_of` of every figure, and cite
  `data.citations`.
- Repeat the `caveats` that apply. Say where the systems disagree or cannot be joined.
- When Kiosk KAI cannot answer, call `core.report_gap` and say what is missing; never guess.

Known joins and gaps (2026-10-29):
- `sbi_branches` holds Gujarat and Chandigarh branches only. Since commit 6cd377f a qualified lead gets a branch only
  if one of ours is within 50 km, so leads elsewhere have no branch (before it, they were matched to a Gujarat branch
  hundreds of km away). Compare those leads by their own state.
- The form's AutoGMap leads hold a placeholder `utm_campaign` (our links, built in `src/routers/tracking.py`, carry the
  real name), so a form lead cannot be tied to one of our campaigns yet.
- TARA names some districts differently: Mohali is "Sahibzada Ajit Singh Nagar", Amroha "Jyotiba Phule Nagar".
- Punjab: 7,010 businesses found, none messaged yet.
