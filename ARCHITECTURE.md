# AutoGMap's architecture: from one monolith to modules

AutoGMap is to become a product. The plan, agreed on 22 Nov 2026, is a **modular
monolith first, not microservices**: one codebase and one deployment, cut into
modules with clear edges. A module becomes its own service only when it truly needs
to.

| Phase | What | State |
|---|---|---|
| 1 | One image, three containers: website/API, worker, scraper (`APP_ROLE`, `src/roles.py`); a work queue in the database between them; System health on Agent Quality | Done, deployed 22 Nov 2026 |
| 2 | Modules with edges a test enforces; adapters for outside services | **Started 22 Nov 2026** |
| 3 | Eko's own rules (SBI/ESAF, amounts, documents, FAQ, dispositions, branches, the bot's journey) out of the code and into configuration; multi-tenancy if SaaS | Waits on one decision: SaaS or a separate installation per client |
| 4 | A module becomes a service of its own only when it must | Later |

## The modules

Every file under `src/` belongs to exactly one module. The map is
`src/architecture/modules.py`.

| Module | What it owns | Examples |
|---|---|---|
| **platform** | The app's own plumbing: database, settings, sign-in, audit, switches, work queue, health | `auth_service`, `agent_controls`, `work_queue`, `system_health` |
| **integrations** | Adapters to outside services. They know nothing of the business. | `meta_whatsapp_service`, `gemini_client`, `google_drive`, `notifier`, `eko_acquisition_client`, `transcribe`, `kiosk_kai` |
| **discovery** | Finding businesses on Google Maps | `discovery_autopilot`, `discovery_engine`, `job_manager`, `sbi_branches` |
| **campaigns** | Messaging businesses: templates, campaigns, links, opt-outs | `whatsapp_service`, `campaign_buttons`, `opt_out` |
| **conversation** | The Inbox, the onboarding bot, its knowledge, tickets, reminders | `inbox`, `onboarding_bot`, `eko_knowledge`, `tickets`, `nudges` |
| **crm** | After someone applies: applications, dispositions, follow-ups, calls, the journey | `applications`, `dispositions`, `followups`, `call_recordings`, `acquisition_handover` |
| **studio** | Writing templates and posters with AI | `template_studio`, `business_agent`, `poster_renderer` |
| **insights** | What works and what to do next | `campaign_insights`, `growth_plan`, `business_context` |

**The rules**

- Anyone may use **platform** and **integrations**.
- An **adapter never imports a business module**. The test enforces this for every adapter, with no exceptions.
- A business module should not reach into another business module's files.
  - When the map was drawn there were **212** such reaches; now there are **207**.
  - They are listed in `src/architecture/baseline.json`.
  - The test suite (`tests/test_architecture.py`) fails on any reach that is not in that list, so the count can only go down.
  - When one is removed, shrink the list:

```bash
python -m src.architecture.boundaries            # the report, by module
python -m src.architecture.boundaries --update   # rewrite the baseline after removing reaches
```

`main.py`, `background.py`, `worker.py`, `models/__init__.py` and `evals/` put the
modules together, so they are not checked.

## Where the reaches are (22 Nov 2026)

| From | To |
|---|---|
| crm | conversation 55, campaigns 8, discovery 6, insights 3 |
| conversation | crm 27, campaigns 17, discovery 9, studio 5, insights 1 |
| studio | campaigns 10, conversation 3, insights 3, discovery 2 |
| campaigns | conversation 7, discovery 6, studio 2, crm 1, insights 1 |
| insights | conversation 5, discovery 5, campaigns 4, crm 3, studio 3 |
| platform | conversation 6, campaigns 5, discovery 3, crm 2, studio 2, insights 1 |
| discovery | conversation 2 |

crm and conversation are the most tangled (82 reaches between them). Both work on
the same tables: the conversation, its bot state and its follow-ups (`models/inbox.py`).

## Phase 2: what comes next, in order

1. **Adapters, done 22 Nov 2026.** Google Drive (`google_drive`) and Eko Acquisition
   (`eko_acquisition_client`) were split from the business code that used them.
   `retention` now trashes Drive files through the adapter.
2. **A provider interface for each outside service.** One small interface per kind
   (messaging, AI text and image, file storage, email, CRM hand-over), with the
   current service as its first implementation. Switching a client to another
   WhatsApp provider or another AI model then means a new adapter, not a change
   across the code.
3. **A public face per module.** Each business module gets one file that the others
   use (for example `conversation.api`): "the person's language", "raise a ticket",
   "record a disposition". The reaches are moved onto it, one module at a time,
   starting with crm and conversation.
4. **Each table owned by one module.** `models/inbox.py` holds tables of two modules.
   It is split so that each module owns its own, and the others read them through
   that module's face.
5. **Events for "something happened".** Today, "documents submitted" calls crm,
   Drive and email directly. Instead, a module announces what happened and the
   others listen. The work queue from Phase 1 can carry these events, so a slow
   listener never holds up the bot.

Each step keeps every test green, and leaves the baseline shorter than it was.
