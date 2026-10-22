# Lead journey: where each step is recorded

A lead's journey is not written as a separate event log. It is **read from the records AutoGMap already keeps**, so leads from before the journey existed have one too. `src/services/lead_journey.py` builds it; `src/services/lead_journey_store.py` copies it every 15 minutes into `lead_journeys` and `lead_journey_steps` for SQL.

AutoGMap's part ends at **"Physical visit required"** (documents uploaded): the lead then goes to **Eko Acquisition**.

## Steps of the journey (stages, in order)

| Step | Recorded in | Written by |
|---|---|---|
| Campaign message sent | `whatsapp_campaign_recipients.sent_at` | `whatsapp_service.py` (campaign send) |
| Delivered / read | `whatsapp_campaign_recipients.delivered_at`, `read_at`, `failed_at` | `routers/whatsapp.py` webhook → `_apply_status_event` |
| Clicked the link | `whatsapp_link_clicks` (`automated_reason` empty = a person) | `routers/tracking.py` (`/r/{token}`) |
| Tapped a button | `whatsapp_button_clicks` | webhook → `_apply_inbound_message` |
| Became interested | the bot's reply `language_prompt` (or `ask_pin`) in `whatsapp_messages` | `onboarding_bot.py` |
| Chose language | the bot's `ask_pin` reply | `onboarding_bot.py` |
| PIN code we serve | the bot's `ask_education` reply; PIN in `whatsapp_conversations.bot_data.coverage` | `onboarding_bot._on_pin` |
| Education met | the bot's `invest_explained` / `ask_invest` reply; `bot_data.education` | `onboarding_bot.py` (`_education_answer`, `education_in_words`) |
| Can invest ₹5 lakh | the bot's `ask_docs` reply; `bot_data.can_invest` | `onboarding_bot.py` |
| Documents ready | the bot's `send_link` reply; `whatsapp_conversations.upload_token`; disposition `int_docs_pending` (Documents pending) recorded by the bot, with its `docs_reminder` follow-up | `onboarding_bot._send_upload_link` → `handover.record`, `followups.mark_sent` |
| Documents uploaded | `whatsapp_conversations.documents_submitted_at`; files in `onboarding_documents` | `routers/onboarding.py` → `onboarding_bot.documents_submitted` |
| Handed to Eko Acquisition | `follow_ups` row with `wants = 'eko_acquisition_api'` | `followups.hand_over` (on upload, or "Physical visit required") → `acquisition_handover.send` |

Each bot step is recognised by the text of the bot's reply, in any language (`lead_journey.classify`). The person's step is dated by their message just before it.

## Where it ends otherwise

| Ending | Recorded in | Written by |
|---|---|---|
| PIN outside our area | bot reply `not_served` (offers Eko's other proposals apart from SBI); `bot_step = NOT_SERVED`; disposition `rej_outside_area` recorded by the bot with its `other_options` follow-up; the team is emailed (the sheet's owner is Bot - Human) | `onboarding_bot._on_pin` → `handover.record`, `followups.mark_sent` |
| Below 12th | bot reply `not_eligible` (a polite no: every bank needs 12th pass); `bot_step = NOT_ELIGIBLE` | `onboarding_bot.py` |
| Cannot invest | bot reply `not_investing`; disposition `ni_investment` recorded by the bot | `onboarding_bot.py` → `handover.record` |
| Any disposition the team records | `chat_activity` (`kind = 'disposition'`), `whatsapp_conversations.disposition` | `handover.record` (inbox) |

## Events along the way

| Event | Recorded in | Written by |
|---|---|---|
| Every message, in and out | `whatsapp_messages` | `inbox.record_inbound`, `inbox.send`, `inbox.send_template` |
| Reminder after an hour of silence | bot reply `nudge` | `nudges.py` |
| Question for the team (ticket) | `attention_tickets`; `whatsapp_conversations.needs_attention` | `onboarding_bot.flag`, `tickets.raise_or_update` |
| Team takes over / hands back | `chat_activity` (`to_person`, `to_bot`) | `handover.take_over`, `handover.hand_back` |
| Nudge planned, sent, answered, RNR, undelivered | `follow_ups` | `followups.plan`, `followups.tick` |
| Task for the team or the District Coordinator | `follow_ups` with `wants = 'task'`; when done, `done_by`, `done_at` and the outcome in `note` ("Spoke to them: …") | `followups.plan`, `followups.complete_task` |
| Backfill of older leads' taps and replies | `whatsapp_messages`, `whatsapp_button_clicks` (a tap the webhook already recorded is skipped) | `inbox.backfill_from_leads` |

## Checks

`journey_checks.py` flags a lead whose steps do not add up (a tap or reply with no sent message, read with no delivered update, documents without the qualifying answers, documents not queued for Eko Acquisition). It shows on the Dashboard; it only reads. A second Dashboard alert flags missing dispositions and missing or overdue action items.

Overdue (`journey_checks.late`, `ticket_late`): a nudge an hour past due; one waiting for its template a day past due; a team or District Coordinator task open 2 days; a question for the team unanswered a day; the hand-over to Eko Acquisition failed or waiting a day.

## Action items queue

Applications → Dispositions → **Action items** (`GET /api/v1/inbox/followups/queue`, `followups.queue`): every open follow-up and every open question for the team, across the leads, filtered by owner (Bot, Team, District Coordinator, Eko Acquisition) and split into **Overdue** (the rules above), **Today** (due before midnight IST) and **Upcoming**. The team's test numbers are left out. Marking a task done needs an outcome (`followups.TASK_OUTCOMES`: Done as asked, Spoke to them, Could not reach them, Not needed any more) and takes an optional note; a question is answered in the chat.

## Disposition mix

Campaign History → Campaign Insights → **Dispositions** (`GET /api/v1/whatsapp/insights/dispositions`, `lead_journey.disposition_mix`): each person a campaign reached, under the latest campaign sent to them, its template and their business's state, counted by their disposition now (`handover.current`, as in the Inbox). Someone who never wrote back and has no recorded disposition is "No reply yet". Test campaigns (under 10 people) are left out.

## Tests

`tests/test_whatsapp_inbox.py`: the journey's steps and their order, negative endings, the stored tables and their refresh, open action items, every check above, the follow-ups (RNR, unreachable, retries, templates), the hand-over to Eko Acquisition, every event writer (inbound messages, template sends, taps, the backfill, tickets, take-over and hand-back, Documents pending and Outside our area recorded by the bot), marking a task done with its outcome, the action items queue, and the disposition mix. Delivered/read and link clicks: `tests/test_whatsapp_delivery_webhook.py`, `tests/test_whatsapp_module.py`.
