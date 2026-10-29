"""
Kiosk KAI in the feedback loop: the client, TARA live in the business data,
and the growth plan's "after us" part. Nothing here reaches Kiosk KAI.
"""
import json
from collections import Counter

import pytest

from src.services import business_context, growth_plan, kiosk_kai


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    kiosk_kai._cache.clear()
    monkeypatch.delenv("KIOSK_KAI_APP_KEY", raising=False)
    yield
    kiosk_kai._cache.clear()


class Reply:
    def __init__(self, body=None, sse=True, status=200, session="s-1"):
        self.status_code = status
        self.headers = {"content-type": "text/event-stream" if sse else "application/json", "mcp-session-id": session}
        self.text = (f"event: message\ndata: {json.dumps(body)}\n\n" if sse else json.dumps(body)) if body else ""

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def stub_server(monkeypatch, answer):
    sent = []

    def post(url, json=None, headers=None, timeout=None):
        sent.append((json, headers))
        if json["method"] == "initialize":
            return Reply({"jsonrpc": "2.0", "id": 1, "result": {"serverInfo": {"name": "kiosk-kai"}}})
        if json["method"] == "notifications/initialized":
            return Reply(None, sse=False, status=202)
        return Reply({"jsonrpc": "2.0", "id": 2, "result": {
            "content": [{"type": "text", "text": __import__("json").dumps(answer)}], "isError": False}})

    monkeypatch.setattr(kiosk_kai.requests, "post", post)
    return sent


def test_without_the_app_key_nothing_is_called(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("no call without a key")
    monkeypatch.setattr(kiosk_kai.requests, "post", boom)
    assert kiosk_kai.call("autogmap.tara_context") is None


def test_a_tool_is_called_with_the_apps_key_and_kept_a_while(monkeypatch):
    monkeypatch.setenv("KIOSK_KAI_APP_KEY", "app-key")
    sent = stub_server(monkeypatch, {"data": {"x": 1}, "as_of": "2026-10-29T10:00:00+05:30", "caveats": []})
    out = kiosk_kai.call("autogmap.acquisition_funnel", days=30)
    assert out["data"] == {"x": 1}
    body, headers = sent[-1]
    assert body["params"] == {"name": "autogmap.acquisition_funnel",
                              "arguments": {"days": 30, "skill": kiosk_kai.SKILL}}
    assert headers["Authorization"] == "Bearer app-key" and headers["Mcp-Session-Id"] == "s-1"
    calls = len(sent)
    kiosk_kai.call("autogmap.acquisition_funnel", days=30)
    assert len(sent) == calls  # from the cache


def test_an_error_or_an_outage_reads_as_no_answer(monkeypatch):
    monkeypatch.setenv("KIOSK_KAI_APP_KEY", "app-key")
    stub_server(monkeypatch, {"data": None, "error": "forbidden"})
    assert kiosk_kai.call("autogmap.tara_context") is None

    def down(*a, **k):
        raise kiosk_kai.requests.ConnectionError("down")
    kiosk_kai._cache.clear()
    monkeypatch.setattr(kiosk_kai.requests, "post", down)
    assert kiosk_kai.call("autogmap.tara_context") is None


def test_taras_figures_are_read_live_over_the_export(monkeypatch):
    export = {
        "exported_at": "2026-10-20T23:00:00+00:00",
        "csp_network": {"terminal_status": {"Active": 470, "Inactive": 60},
                        "activity_by_month": {"2026-06": {"csps": 500, "txns": 1}, "2026-10": {"csps": 480, "txns": 2}}},
        "revenue_forecasts": {"Oct-26": {"as_of": "2026-10-20", "accrued_inr": 1}},
        "onboarding": {"applicants": {"total": 9}},
    }
    live = {"data": {"business_context": {
        "csp_network": {"terminal_status": {"Active": 489, "Inactive": 50},
                        "activity_by_month": {"2026-10": {"csps": 486, "txns": 290218}}},
        "revenue_forecasts": {"Oct-26": {"as_of": "2026-10-27", "accrued_inr": 7411152}}}},
        "as_of": "2026-10-29T10:50:03+05:30"}
    monkeypatch.setattr(kiosk_kai, "call", lambda tool, **a: live if tool == "autogmap.tara_context" else None)
    ctx = business_context.with_live_tara(export)
    assert ctx["csp_network"]["terminal_status"] == {"Active": 489, "Inactive": 50}
    # A month only the export has is kept; one Kiosk KAI has is the live one.
    assert ctx["csp_network"]["activity_by_month"]["2026-06"] == {"csps": 500, "txns": 1}
    assert ctx["csp_network"]["activity_by_month"]["2026-10"]["txns"] == 290218
    assert ctx["revenue_forecasts"]["Oct-26"]["accrued_inr"] == 7411152
    assert ctx["onboarding"] == export["onboarding"] and ctx["tara_live_as_of"] == "2026-10-29T10:50:03+05:30"
    assert business_context.summarise(ctx)["tara_live_as_of"] == "2026-10-29T10:50:03+05:30"

    monkeypatch.setattr(kiosk_kai, "call", lambda tool, **a: None)
    assert business_context.with_live_tara(export) is export


FUNNEL = {"data": {
    "autogmap": {"journeys": {"reached_uploaded": 1}},
    "ekokiosk": {"as_of": "2026-10-29T10:57:53+05:30", "total": {"leads": 28, "qualified": 2},
                 "autogmap_row": {"source": "AutoGMap", "leads": 2, "submitted": 2, "qualified": 2, "with_documents": 0}},
    "tara": {"as_of": "2026-10-29T10:57:53+05:30",
             "in_lead_states": {"csps": 482, "active": 441, "inactive": 41},
             "circles": [{"circle": "Chandigarh", "csps": 167, "active": 145, "inactive": 22}]}},
    "caveats": ["The form's AutoGMap leads hold a placeholder utm_campaign."]}
TARGETS = {"data": {"districts": [
    {"ao": "LUDHIANA", "state": "Punjab", "district": "LUDHIANA", "existing_csps": 8, "replacement_codes": 1, "need_campaign": True},
    {"ao": "MOHALI", "state": "Punjab", "district": "GURDASPUR", "existing_csps": 5, "replacement_codes": 3, "need_campaign": True},
    {"ao": "ROHTAK", "state": "Haryana", "district": "SIRSA", "existing_csps": 33, "replacement_codes": 1, "need_campaign": True},
    {"ao": "X", "state": "Punjab", "district": "PATIALA", "existing_csps": 9, "replacement_codes": 0, "need_campaign": False},
]}, "as_of": "2026-10-29T10:58:00+05:30", "caveats": []}


def test_the_plan_says_what_happens_after_us_and_where_campaigns_are_needed(monkeypatch):
    answers = {"autogmap.acquisition_funnel": FUNNEL, "ekokiosk.campaign_targets": TARGETS}
    monkeypatch.setattr(kiosk_kai, "call", lambda tool, **a: answers.get(tool))
    pool = {"district": Counter({"Ludhiana": 120, "Sirsa": 7, "Ahmedabad": 900}), "category": Counter(), "pair": Counter()}
    out = growth_plan.beyond(pool)
    assert out["form"]["autogmap"] == {"leads": 2, "submitted": 2, "qualified": 2, "with_documents": 0}
    assert out["tara"]["in_lead_states"]["inactive"] == 41
    # Places to fill first, then where we can message today; one the sheet does not need is left out.
    assert [d["district"] for d in out["need_campaign"]] == ["GURDASPUR", "LUDHIANA", "SIRSA"]
    assert [d["left"] for d in out["need_campaign"]] == [0, 120, 7]
    assert out["caveats"]

    steps = growth_plan.next_steps({"still_needed": 0, "messages_needed": None}, {"biggest_leak": None}, [],
                                   {"districts": [], "categories": [], "judged_on": "responded"},
                                   {"untried_angles": [], "untried_layouts": []}, {}, out)
    titles = [s["title"] for s in steps]
    assert titles[0] == "Message the districts Eko's targeting sheet needs"
    assert "Ludhiana (Punjab): 120 businesses not yet messaged, 1 CSP place to fill" in steps[0]["detail"]
    assert "Gurdaspur (Punjab)" in steps[1]["detail"]

    text = growth_plan._beyond_text(out)
    assert "2 applications came from AutoGMap" in text and "Gurdaspur (Punjab)" in text


def test_without_kiosk_kai_the_plan_has_no_after_us_part(monkeypatch):
    monkeypatch.setattr(kiosk_kai, "call", lambda tool, **a: None)
    assert growth_plan.beyond({"district": Counter(), "category": Counter(), "pair": Counter()}) is None
    assert growth_plan._beyond_text(None) == ""
