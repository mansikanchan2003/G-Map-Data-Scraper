"""
AutoGMap's modules (Phase 2 of moving off one monolith, 22 Nov 2026).

The code stays one deployable app (src.roles splits it into containers), but each file
belongs to one module, and a module should reach another only through what that module
offers, never into its insides. This file is the map; src.architecture.boundaries checks
the code against it, and the test suite fails on any new reach across that the baseline
does not already list. Phase 2 is done when the baseline is empty.

Two modules everything may use:
- platform: the app's own plumbing (database, settings, sign-in, audit, switches,
  the work queue, health).
- integrations: adapters to outside services (WhatsApp, AI models, Google, email,
  Eko's APIs, speech-to-text). An adapter knows nothing of the business: it must not
  import a business module.
"""
from typing import Dict, List

# Module -> its files, as paths under src/ without ".py". A directory entry ("utils/")
# takes every file in it.
MODULES: Dict[str, List[str]] = {
    "platform": [
        "config", "database", "roles", "background", "worker", "main", "architecture/",
        "utils/", "schemas/common", "evals/",
        "services/auth_service", "services/audit", "services/agent_controls", "services/agent_telemetry",
        "services/system_health", "services/work_queue", "services/retention",
        "routers/auth", "routers/system", "routers/agents",
        "models/__init__", "models/user", "models/audit", "models/app_setting", "models/agent_runs",
        "models/work_queue",
    ],
    "integrations": [
        "services/meta_whatsapp_service", "services/gemini_client",
        "services/google_sheets", "services/notifier", "services/email_html", "services/email_i18n",
        "services/eko_digilocker", "services/kiosk_kai", "services/transcribe",
        "services/google_drive", "services/eko_acquisition_client",
    ],
    # Finding businesses on Google Maps: places, categories, jobs, the scraper and its autopilot.
    "discovery": [
        "services/discovery_autopilot", "services/discovery_engine", "services/email_enricher",
        "services/job_manager", "services/config_loader", "services/custom_target", "services/deduplicator",
        "services/normalizer", "services/geo_bounds", "services/geo_validator", "services/sbi_branches",
        "services/partners", "services/business_pin", "services/dc_network",
        "routers/discovery", "routers/jobs", "routers/config", "routers/businesses", "routers/partners",
        "routers/runs", "routers/export",
        "models/location", "models/category", "models/job", "models/business", "models/run_log",
        "models/autopilot", "models/sbi_branch",
        "schemas/business", "schemas/category", "schemas/job", "schemas/location", "schemas/run_log",
    ],
    # Messaging businesses: templates on Meta, campaigns, tracking links, opt-outs.
    "campaigns": [
        "services/whatsapp_service", "services/campaign_buttons", "services/campaign_approval",
        "services/whatsapp_normalizer", "services/click_filter", "services/opt_out", "services/pricing",
        "services/number_usage", "services/sheet_templates",
        "routers/whatsapp", "routers/tracking", "routers/audience",
        "models/whatsapp", "models/opt_out", "schemas/whatsapp",
    ],
    # The conversation: the Inbox, the onboarding bot, its knowledge, tickets and reminders.
    "conversation": [
        "services/inbox", "services/onboarding_bot", "services/bot_messages", "services/eko_knowledge",
        "services/faq_learning", "services/chat_documents", "services/chat_summary", "services/tickets",
        "services/nudges", "services/nudge_messages", "services/nudge_templates", "services/auto_replies",
        "services/reply_dispositions", "services/reply_language", "services/claude_answers",
        "services/bot_coach", "services/learning_loop", "services/interest_rules",
        "services/documents_report", "services/dc_meet", "services/dc_visit", "services/pincode_coverage",
        "services/drive_uploads",
        "routers/inbox", "routers/onboarding",
        "models/inbox",
    ],
    # After someone applies: applications, dispositions, follow-ups, calls, the lead journey.
    "crm": [
        "services/applications", "services/qualified_leads", "services/dispositions", "services/handover",
        "services/followups", "services/contact_channels", "services/lead_journey",
        "services/lead_journey_store", "services/journey_checks", "services/report_store",
        "services/call_plan", "services/call_script", "services/call_programme", "services/ai_calls",
        "services/call_recordings", "services/acquisition_handover",
        "routers/applications", "routers/ai_calls", "routers/call_recorder",
        "models/application", "models/reports",
    ],
    # Writing templates and posters with AI.
    "studio": [
        "services/template_studio", "services/business_agent", "services/creative_brief",
        "services/image_prompts", "services/poster_layouts", "services/poster_renderer",
        "services/real_photos", "services/reference_posters", "services/photo_queue", "services/variety",
        "routers/template_studio",
        "models/studio",
    ],
    # What works and what to do next: campaign insights, the growth plan, business figures.
    "insights": [
        "services/campaign_insights", "services/growth_plan", "services/business_context",
        "services/insights_cache",
        "routers/insights",
        "models/insights",
    ],
}

# Everyone may use these.
SHARED = ("platform", "integrations")
