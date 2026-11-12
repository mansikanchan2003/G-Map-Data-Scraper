"""
The Applications tab: who has applied through the WhatsApp onboarding bot,
how far they got, and whether they qualify.

Strongly qualified is the team's definition: a PIN in our area, at least
12th / Diploma, and Yes to investing ₹3–5 lakh.
"""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base, get_db
from src.main import app
from src.models import ApplicationRemoval
from src.models.inbox import OnboardingDocument, WhatsAppConversation, WhatsAppMessage
from src.services import onboarding_bot as bot

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

SERVED = {"pincode": "363520", "place": "Chotila", "distance_km": 0.0, "served": True}

PEOPLE = {
    # phone: (name, step, bot_data, submitted)
    "+919000000001": ("Strong & submitted", bot.SUBMITTED,
                      {"coverage": SERVED, "education": "grad", "franchise": True, "can_invest": True}, True),
    "+919000000002": ("Strong, no docs yet", bot.AWAIT_UPLOAD,
                      {"coverage": SERVED, "education": "12", "franchise": False, "can_invest": True}, False),
    "+919000000003": ("Below 12th", bot.NOT_ELIGIBLE, {"coverage": SERVED, "education": "other"}, False),
    # Recorded before the PIN result was kept: a not-served PIN ends at NOT_SERVED.
    "+919000000004": ("Outside the area", bot.NOT_SERVED, {"coverage": {"pincode": "110001"}}, False),
    "+919000000005": ("Cannot invest", bot.NOT_INVESTING,
                      {"coverage": SERVED, "education": "12", "franchise": False, "can_invest": False}, False),
    "+919000000006": ("Asked for PIN", bot.AWAIT_PIN, {"pin_attempts": 0}, False),
    "+919000000007": ("Webinar only", bot.WEBINAR_CONFIRMED, {"webinar": {"answer": "yes"}}, False),
    "+919000000008": ("Never in the bot", None, None, False),
    # In the bot, but no AutoGMap campaign reached them: another team's contact.
    "+919000000009": ("Existing CSP", bot.AWAIT_PIN, {"pin_attempts": 0}, False),
}
NOT_OURS = {"+919000000009"}


GEO = {"363520": {"state": "Gujarat", "district": "Surendranagar", "tehsil": "Chotila"},
       "110001": {"state": "Delhi", "district": "New Delhi", "tehsil": None}}
COORDS = {"363520": (22.42, 71.19), "110001": (28.63, 77.22)}
LOOKUPS = []


def _locate(pin):
    if pin not in COORDS:
        raise LookupError(pin)
    return COORDS[pin]


@pytest.fixture
def client(monkeypatch):
    from src.services import pincode_coverage
    LOOKUPS.clear()
    monkeypatch.setattr(pincode_coverage, "geography",
                        lambda db, pin: LOOKUPS.append(pin) or GEO.get(pin))
    monkeypatch.setattr(pincode_coverage, "locate", _locate)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    now = datetime.now(timezone.utc)
    for phone, (name, step, data, submitted) in PEOPLE.items():
        db.add(WhatsAppConversation(phone=phone, profile_name=name, bot_step=step, bot_data=data,
                                    last_message_at=now, documents_submitted_at=now if submitted else None))
    db.flush()
    from src.models.whatsapp import WhatsAppCampaign, WhatsAppCampaignRecipient
    db.add(WhatsAppCampaign(campaign_id="C0", name="Earlier campaign", data_source_type="scraped", status="COMPLETED",
                            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))
    for i, phone in enumerate(p for p in PEOPLE if p not in NOT_OURS):
        db.add(WhatsAppCampaignRecipient(recipient_id=f"R0-{i}", campaign_id="C0", phone=phone, status="DELIVERED",
                                         provider_message_id=f"wamid.0.{i}"))
    for key in ("pan", "aadhaar", "photo", "cibil"):
        db.add(OnboardingDocument(document_id=f"d-{key}", phone="+919000000001", doc_type=key,
                                  original_name=f"{key}.pdf", stored_path=f"/x/{key}.pdf",
                                  content_type="application/pdf", size_bytes=10))
    db.add(OnboardingDocument(document_id="d2-pan", phone="+919000000002", doc_type="pan",
                              stored_path="/x/p.pdf", content_type="application/pdf", size_bytes=10))
    db.commit()
    db.close()

    def override():
        s = TestingSessionLocal()
        try:
            yield s
        finally:
            s.close()

    from src.models import User
    from src.routers.auth import current_user
    app.dependency_overrides[get_db] = override
    app.dependency_overrides[current_user] = lambda: User(email="reviewer@eko.co.in", full_name="Reviewer",
                                                          role="manager", status="APPROVED")
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(current_user, None)


def _by_phone(client, **params):
    out = client.get("/api/v1/applications", params=params).json()
    return out["stats"], {a["phone"]: a for a in out["items"]}


def test_people_in_the_onboarding_or_guidance_flow_are_applications(client):
    stats, apps = _by_phone(client)
    assert set(apps) == {f"+91900000000{i}" for i in range(1, 8)}
    assert stats["total"] == 7
    # Asking for personal guidance counts, shown at its own stage.
    assert apps["+919000000007"]["stage"] == bot.STEP_LABELS[bot.WEBINAR_CONFIRMED]
    assert apps["+919000000007"]["verdict"] == "In progress"


def test_the_totals_follow_the_teams_definitions(client):
    stats, apps = _by_phone(client)
    assert stats == {"total": 7, "pin_qualified": 4, "strongly_qualified": 2,
                     "not_qualified": 3, "submitted": 1, "removed": 0}
    assert apps["+919000000001"]["verdict"] == "Strongly qualified"
    assert apps["+919000000002"]["strongly_qualified"] is True
    assert apps["+919000000003"]["not_qualified_reasons"] == ["Below 12th"]
    assert apps["+919000000004"]["not_qualified_reasons"] == ["Not qualified for SBI branch code"]
    assert apps["+919000000004"]["verdict"] == "Not qualified for SBI branch code"
    assert apps["+919000000005"]["not_qualified_reasons"] == ["Cannot invest ₹3–5 lakh"]
    assert apps["+919000000006"]["verdict"] == "In progress"


def test_each_row_shows_qualification_stage_and_documents(client):
    _, apps = _by_phone(client)
    first = apps["+919000000001"]
    assert first["qualification"] == "Graduate / Post-Grad"
    assert first["stage"] == "Documents submitted"
    assert (first["documents_count"], first["documents_total"]) == (4, len(bot.DOCUMENTS))
    assert first["required_documents_done"] is True and first["submitted"] is True
    second = apps["+919000000002"]
    assert second["qualification"] == "12th / Diploma"
    assert second["required_documents_done"] is False


def test_comments_are_added_shown_and_deleted(client):
    r = client.post("/api/v1/applications/919000000002/comments", json={"body": "Called, will upload tonight"})
    assert r.status_code == 200, r.text
    _, apps = _by_phone(client)
    [c] = apps["+919000000002"]["comments"]
    assert c["body"] == "Called, will upload tonight" and c["author"]
    assert client.delete(f"/api/v1/applications/comments/{c['comment_id']}").status_code == 200
    _, apps = _by_phone(client)
    assert apps["+919000000002"]["comments"] == []


def test_a_comment_on_someone_who_has_not_applied_is_refused(client):
    r = client.post("/api/v1/applications/919000000008/comments", json={"body": "x"})
    assert r.status_code == 404


def test_removing_keeps_the_chat_and_restore_brings_it_back(client):
    assert client.delete("/api/v1/applications/919000000005").status_code == 200
    stats, apps = _by_phone(client)
    assert "+919000000005" not in apps and stats["total"] == 6 and stats["removed"] == 1
    _, removed = _by_phone(client, removed=True)
    assert list(removed) == ["+919000000005"]

    db = TestingSessionLocal()
    assert db.get(WhatsAppConversation, "+919000000005") is not None  # the Inbox keeps it
    db.close()

    assert client.post("/api/v1/applications/919000000005/restore").status_code == 200
    stats, apps = _by_phone(client)
    assert "+919000000005" in apps and stats["removed"] == 0


def test_the_bot_now_records_whether_a_pin_was_served(monkeypatch):
    from src.services import pincode_coverage
    monkeypatch.setattr(pincode_coverage, "check",
                        lambda db, pin: {"status": "not_served", "pincode": pin, "distance_km": 80.0})
    monkeypatch.setattr(bot, "_say", lambda *a, **k: None)
    monkeypatch.setattr(bot, "_t", lambda *a, **k: "")
    monkeypatch.setattr(bot, "_lang", lambda *a, **k: "en")
    conv = WhatsAppConversation(phone="+919000000099", bot_step=bot.AWAIT_PIN, bot_data={})
    msg = WhatsAppMessage(message_id="m", phone=conv.phone, direction="IN", kind="text", body="110001")
    bot._on_pin(None, conv, msg)
    # Outside our area, they carry on (2026-10-23); the note says the PIN was not served.
    assert conv.bot_data["coverage"]["served"] is False and conv.bot_step == bot.AWAIT_EDUCATION


def test_each_application_shows_its_own_state_district_and_tehsil(client):
    _, apps = _by_phone(client)
    assert (apps["+919000000001"]["state"], apps["+919000000001"]["district"], apps["+919000000001"]["tehsil"]) ==         ("Gujarat", "Surendranagar", "Chotila")
    assert apps["+919000000004"]["district"] == "New Delhi" and apps["+919000000004"]["tehsil"] is None
    assert apps["+919000000006"]["state"] is None  # no PIN given yet


def test_a_pin_is_looked_up_once_and_kept(client):
    _by_phone(client)
    first = len(LOOKUPS)
    assert first == 5  # five applications have a PIN
    _by_phone(client)
    assert len(LOOKUPS) == first


def _add_branches():
    from src.models.location import Location
    from src.models.sbi_branch import SbiBranch
    db = TestingSessionLocal()
    for code, name, pin, ao, (lat, lng) in [("60104", "Chotila", "363520", "AO Ahmedabad", (22.42, 71.19)),
                                            ("497", "Viramgam", "382150", "AO Ahmedabad", (23.12, 72.04)),
                                            ("60086", "Vinchhiya", "360055", "AO Rajkot", (22.21, 71.38))]:
        db.add(SbiBranch(branch_code=code, branch_name=name, pincode=pin, module=ao))
        db.add(Location(location_id=f"loc-{pin}", pincode=pin, latitude=lat, longitude=lng,
                        radius_km=10, anchor_name=name, source_dataset="sbi_branches"))
    db.commit()
    db.close()


def test_each_application_shows_its_nearest_sbi_branch_and_ao(client):
    _add_branches()
    _, apps = _by_phone(client)
    assert apps["+919000000001"]["sbi_branch"] == {"branch_code": "60104", "branch_name": "Chotila",
                                                   "ao": "AO Ahmedabad", "pincode": "363520", "distance_km": 0.0}
    # Far away, still the nearest of the branches, with how far it is.
    # Delhi is over 700 km from any of our (Gujarat) branches: none is its branch.
    assert apps["+919000000004"]["sbi_branch"] is None
    assert apps["+919000000006"]["sbi_branch"] is None  # no PIN given yet


def test_a_branch_added_later_is_found_without_looking_the_pin_up_again(client):
    _, apps = _by_phone(client)
    assert apps["+919000000001"]["sbi_branch"] is None  # no branches yet
    looked_up = len(LOOKUPS)
    _add_branches()
    _, apps = _by_phone(client)
    assert apps["+919000000001"]["sbi_branch"]["branch_code"] == "60104"
    assert len(LOOKUPS) == looked_up


def test_a_pin_the_bot_could_not_place_comes_from_the_chat(client):
    db = TestingSessionLocal()
    for i, body in enumerate(["Interested", "mera pin 363 520 hai", "ok"]):
        db.add(WhatsAppMessage(message_id=f"m{i}", phone="+919000000006", direction="IN", kind="text", body=body,
                               created_at=datetime(2026, 10, 13, 10, i, tzinfo=timezone.utc)))
    db.commit()
    db.close()
    _, apps = _by_phone(client)
    asked = apps["+919000000006"]
    assert asked["pincode"] == "363520" and asked["pincode_unchecked"] is True
    assert asked["district"] == "Surendranagar"
    checked = apps["+919000000001"]
    assert checked["pincode"] == "363520" and checked["pincode_unchecked"] is False


def test_the_persona_is_the_category_the_business_was_found_as(client):
    from src.models import Business
    from src.models.whatsapp import WhatsAppCampaign, WhatsAppCampaignRecipient
    db = TestingSessionLocal()
    db.add(Business(business_id="B1", job_id="J1", name="Patel Xerox", phone="+919000000001", category="Copy shop",
                    state="Gujarat", district="Surendranagar", source_query="q", dedup_key="k1"))
    db.add(WhatsAppCampaign(campaign_id="C1", name="Gujarat copy shops", data_source_type="scraped", status="COMPLETED"))
    db.add(WhatsAppCampaign(campaign_id="C2", name="Sheet upload", data_source_type="upload", status="COMPLETED"))
    db.add(WhatsAppCampaignRecipient(recipient_id="R1", campaign_id="C1", phone="+919000000001", business_id="B1",
                                     status="DELIVERED", provider_message_id="wamid.1"))
    db.add(WhatsAppCampaignRecipient(recipient_id="R2", campaign_id="C2", phone="+919000000002", name="Sunita",
                                     variables={"Category": "Kiosk"}, status="SENT", provider_message_id="wamid.2"))
    db.commit()
    db.close()
    _, apps = _by_phone(client)
    assert apps["+919000000001"]["category"] == "Copy shop"
    assert apps["+919000000002"]["category"] == "Kiosk"  # from the uploaded sheet's column
    assert apps["+919000000003"]["category"] is None    # not reached by a campaign


def test_someone_no_campaign_reached_is_not_an_application(client):
    stats, apps = _by_phone(client)
    assert "+919000000009" not in apps and stats["total"] == 7


def test_digits_inside_a_csp_code_are_not_a_pin(client):
    db = TestingSessionLocal()
    for i, body in enumerate(["425414", "Aapka CSP code?", "1A851679"]):
        db.add(WhatsAppMessage(message_id=f"c{i}", phone="+919000000006", direction="IN", kind="text", body=body,
                               created_at=datetime(2026, 10, 13, 11, i, tzinfo=timezone.utc)))
    db.commit()
    db.close()
    _, apps = _by_phone(client)
    assert apps["+919000000006"]["pincode"] == "425414"


def test_several_comments_are_kept_in_order_each_with_its_date(client):
    for body in ("Reached him, asked for CIBIL", "Called back: CIBIL sent, will submit tonight", "Submitted, forwarded to SBI"):
        assert client.post("/api/v1/applications/919000000002/comments", json={"body": body}).status_code == 200
    _, apps = _by_phone(client)
    comments = apps["+919000000002"]["comments"]
    assert [c["body"] for c in comments] == ["Reached him, asked for CIBIL",
                                             "Called back: CIBIL sent, will submit tonight", "Submitted, forwarded to SBI"]
    assert all(c["created_at"] and c["author"] == "Reviewer" for c in comments)


def test_each_row_says_when_the_lead_came_in(client):
    # Their first message or tap, not a later one, and not our own messages.
    db = TestingSessionLocal()
    at = lambda h: datetime(2026, 10, 14, h, 0, tzinfo=timezone.utc)
    for i, (direction, hour) in enumerate([("OUT", 6), ("IN", 8), ("IN", 9)]):
        db.add(WhatsAppMessage(message_id=f"lead-{i}", phone="+919000000002", direction=direction,
                               kind="text", body="x", created_at=at(hour)))
    db.commit()
    db.close()
    _, apps = _by_phone(client)
    assert apps["+919000000002"]["lead_at"].startswith("2026-10-14T08:00")
    # With no message of theirs recorded, when the conversation began.
    assert apps["+919000000001"]["lead_at"] == apps["+919000000001"]["started_at"]


def test_qualified_and_strongly_qualified_leads_are_kept_with_the_nearest_branch(client, monkeypatch):
    from src.models import Location, QualifiedLead
    from src.models.sbi_branch import SbiBranch
    from src.services import pincode_coverage
    db = TestingSessionLocal()
    # Two of our branches, and someone part-way: PIN in our area, education not answered yet.
    db.add(SbiBranch(branch_code="60108", branch_name="MULI", pincode="363510", circle="GANDHINAGAR",
                     module="AO Ahmedabad", region="5"))
    db.add(SbiBranch(branch_code="60077", branch_name="JASDAN", pincode="360050", circle="GANDHINAGAR",
                     module="AO RAJKOT", region="6"))
    db.add(Location(location_id="L1", pincode="363510", latitude=22.65, longitude=71.46))
    db.add(Location(location_id="L2", pincode="360050", latitude=22.04, longitude=71.20))
    db.add(WhatsAppConversation(phone="+919000000010", profile_name="Part-way", bot_step=bot.AWAIT_EDUCATION,
                                bot_data={"coverage": SERVED}, last_message_at=datetime.now(timezone.utc)))
    from src.models.whatsapp import WhatsAppCampaignRecipient
    db.add(WhatsAppCampaignRecipient(recipient_id="R0-x", campaign_id="C0", phone="+919000000010",
                                     status="DELIVERED", provider_message_id="wamid.0.x"))
    db.commit()
    # Chotila (363520) sits about 25 km from Muli and 60 km from Jasdan.
    def locate(pin):
        if pin != "363520":
            raise LookupError(pin)
        return 22.42, 71.20
    monkeypatch.setattr(pincode_coverage, "locate", locate)

    out = client.get("/api/v1/applications/qualified").json()
    leads = {a["phone"]: a for a in out["items"]}
    assert set(leads) == {"+919000000001", "+919000000002", "+919000000004", "+919000000010"}
    assert out["stats"]["strongly_qualified"] == 2 and out["stats"]["qualified"] == 1
    # A real PIN outside our SBI branch area is kept too, for another proposal (2026-10-23).
    assert out["stats"]["other_proposal"] == 1
    other = leads["+919000000004"]
    assert other["level"] == "Not qualified for SBI branch code" and other["still_qualified"]
    assert other["why"][0].startswith("PIN 110001 is outside our SBI branch area")
    strong = leads["+919000000001"]
    assert strong["level"] == "Strongly qualified" and strong["submitted"]
    assert strong["why"] == ["PIN 363520 is in our area (Chotila)", "Graduate or post-graduate", "Can invest ₹3–5 lakh"]
    assert strong["district"] == "Surendranagar" and strong["pincode"] == "363520"
    assert strong["branch"]["code"] == "60108" and strong["branch"]["ao"] == "AO Ahmedabad"
    part = leads["+919000000010"]
    assert part["level"] == "Qualified" and "Education not answered yet" in part["why"]

    # Saying later they cannot invest does not lose them: kept, marked as dropped.
    conv = db.get(WhatsAppConversation, "+919000000002")
    conv.bot_data = {**conv.bot_data, "can_invest": False}
    conv.bot_step = bot.NOT_INVESTING
    db.commit()
    again = {a["phone"]: a for a in client.get("/api/v1/applications/qualified").json()["items"]}
    assert again["+919000000002"]["level"] == "Strongly qualified"
    assert again["+919000000002"]["still_qualified"] is False
    assert again["+919000000002"]["now"].startswith("Not qualified now: cannot invest")
    assert db.query(QualifiedLead).count() == 4
    # A branch states away, kept before the 50 km limit, is cleared (Mohali was put at Viramgam).
    assert leads["+919000000004"]["branch"] is None
    far = db.get(QualifiedLead, "+919000000004")
    far.branch_code, far.branch_name, far.branch_circle, far.branch_distance_km = "497", "VIRAMGAM", "GANDHINAGAR", 905.0
    delhi = db.get(WhatsAppConversation, "+919000000004")
    delhi.bot_data = {**delhi.bot_data, "coverage": {**delhi.bot_data["coverage"], "coords": [28.63, 77.22]}}
    db.commit()
    client.get("/api/v1/applications/qualified")
    db.refresh(far)
    assert far.branch_code is None and far.branch_circle is None and far.branch_distance_km is None
    db.close()


# --- The call-recorder app's list of numbers (11 Nov 2026) -------------------------------------

KEY = "k" * 32


def test_the_call_recorder_app_gets_only_the_applications_numbers(client, monkeypatch):
    monkeypatch.setenv("CALL_RECORDER_API_KEY", KEY)
    client.delete("/api/v1/applications/919000000005")     # taken off the tab: not recorded
    r = client.get("/api/v1/call-recorder/numbers", headers={"X-API-Key": KEY})
    assert r.status_code == 200
    body = r.json()
    _, apps = _by_phone(client)
    got = {n["phone"]: n for n in body["numbers"]}
    assert set(got) == set(apps) and body["count"] == len(apps)
    assert "+919000000005" not in got and "+919000000008" not in got and "+919000000009" not in got
    assert got["+919000000001"] == {**got["+919000000001"], "local": "9000000001", "name": "Strong & submitted"}
    # Names and numbers only: nothing else about the person.
    assert set(got["+919000000001"]) == {"phone", "local", "name", "since", "test"}
    assert not any(n["test"] for n in body["numbers"])


@pytest.mark.parametrize("server_key, sent", [
    (KEY, None), (KEY, "wrong"), ("", ""), ("short", "short"),
])
def test_the_call_recorder_list_needs_the_right_key(client, monkeypatch, server_key, sent):
    monkeypatch.setenv("CALL_RECORDER_API_KEY", server_key)
    headers = {"X-API-Key": sent} if sent is not None else {}
    assert client.get("/api/v1/call-recorder/numbers", headers=headers).status_code == 401


# --- Call recordings from the call-recorder app (11 Nov 2026) ----------------------------------

@pytest.fixture
def recordings_dir(tmp_path, monkeypatch):
    from src.services import call_recordings
    monkeypatch.setattr(call_recordings, "RECORDINGS_DIR", str(tmp_path))
    monkeypatch.setenv("CALL_RECORDER_API_KEY", KEY)
    return tmp_path


def _upload(client, phone, rid="r1", data=b"ID3audio", ctype="audio/mpeg", key=KEY):
    return client.post("/api/v1/call-recorder/recordings", headers={"X-API-Key": key},
                       data={"phone": phone, "recording_id": rid, "direction": "incoming",
                             "started_at": "2026-11-11 10:05:00", "duration_seconds": "95"},
                       files={"file": ("call.mp3", data, ctype)})


def test_an_uploaded_recording_of_an_applicant_is_kept_and_shown(client, recordings_dir):
    r = _upload(client, "09000000001")          # the phone's own form of +919000000001
    assert r.status_code == 201
    again = _upload(client, "+91 90000 00001")   # the same recording sent twice: kept once
    assert again.json()["recording_id"] == r.json()["recording_id"]
    rows = client.get("/api/v1/inbox/conversations/919000000001/recordings").json()
    assert len(rows) == 1 and rows[0]["direction"] == "in" and rows[0]["duration_seconds"] == 95
    assert rows[0]["started_at"].startswith("2026-11-11T04:35")     # 10:05 India time
    audio = client.get(f"/api/v1/call-recordings/{rows[0]['recording_id']}/audio")
    assert audio.status_code == 200 and audio.content == b"ID3audio"


def test_a_call_with_someone_not_on_the_applications_tab_is_refused(client, recordings_dir):
    assert _upload(client, "+919000000008").status_code == 422       # never in the bot
    assert _upload(client, "+919811111111").status_code == 422       # anyone else
    assert _upload(client, "+919000000001", ctype="application/pdf", data=b"%PDF").status_code == 422
    assert _upload(client, "+919000000001", key="wrong" * 6).status_code == 401
    assert list(recordings_dir.iterdir()) == []


def test_new_recordings_are_fetched_from_the_apps_endpoint(client, recordings_dir, monkeypatch):
    from src.services import call_recordings
    monkeypatch.setenv("CALL_RECORDINGS_SOURCE_URL", "https://recorder.example/api/recordings")
    calls = []

    class Resp:
        def __init__(self, body=None, content=b"", ctype="audio/mp4"):
            self.body, self.content, self.headers = body, content, {"content-type": ctype}
        def raise_for_status(self):
            pass
        def json(self):
            return self.body

    class Http:
        def get(self, url, headers=None, params=None, timeout=None):
            calls.append(url)
            if url.endswith("/recordings"):
                return Resp({"recordings": [
                    {"id": 1, "number": "+919000000002", "url": "/files/1.m4a", "type": "outgoing", "duration": 30},
                    {"id": 2, "number": "+919811111111", "url": "/files/2.m4a"},       # not an applicant
                ]})
            return Resp(content=b"m4a-bytes")

    db = TestingSessionLocal()
    out = call_recordings.fetch(db, Http())
    assert out["kept"] == 1 and out["skipped"] == 1
    assert "https://recorder.example/files/2.m4a" not in calls            # never downloaded
    assert call_recordings.fetch(db, Http())["kept"] == 0                  # already have it
    rows = call_recordings.for_phone(db, "+919000000002")
    assert len(rows) == 1 and rows[0]["direction"] == "out" and rows[0]["source"] == "pull"
    db.close()


def test_the_zip_for_sumit_has_every_recording_and_only_the_last_digits(client, recordings_dir):
    import io
    import zipfile
    _upload(client, "+919000000001", rid="a")
    _upload(client, "+919000000002", rid="b")
    r = client.get("/api/v1/call-recordings/export")
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = z.namelist()
    assert "recordings.csv" in names and len([n for n in names if n.startswith("recordings/")]) == 2
    csv = z.read("recordings.csv").decode()
    assert "9000000001" not in csv and ",0001" in csv


def test_members_may_not_listen(client, recordings_dir):
    from src.models import User
    from src.routers.auth import current_user
    app.dependency_overrides[current_user] = lambda: User(email="m@eko.co.in", role="member", status="APPROVED")
    assert client.get("/api/v1/call-recordings/export").status_code == 403
    assert client.get("/api/v1/call-recordings/summary").status_code == 403
    assert client.get("/api/v1/call-recordings/numbers.xlsx").status_code == 403


def test_the_call_recorder_excel_has_the_apps_columns_and_the_tabs_people(client):
    import io
    from openpyxl import load_workbook
    r = client.get("/api/v1/call-recordings/numbers.xlsx")
    assert r.status_code == 200 and "spreadsheetml" in r.headers["content-type"]
    ws = load_workbook(io.BytesIO(r.content)).active
    rows = list(ws.iter_rows(values_only=True))
    assert rows[0] == ("Phone", "Name", "Description", "Active")
    _, apps = _by_phone(client)
    assert {row[0] for row in rows[1:]} == {p[-10:] for p in apps}
    assert all(row[3] == "Yes" and row[2] for row in rows[1:])
    assert ws["A2"].number_format == "@"            # the number stays text, never 9.00E+09


def test_the_teams_test_phones_are_listed_and_their_recordings_kept_apart(client, recordings_dir, monkeypatch):
    import io
    import zipfile
    # A team phone, and an applicant's number listed as a test too (the applicant wins).
    monkeypatch.setenv("CALL_RECORDER_TEST_NUMBERS", "+91 98111 22233, 09000000001, 12")
    body = client.get("/api/v1/call-recorder/numbers", headers={"X-API-Key": KEY}).json()
    tests = [n for n in body["numbers"] if n["test"]]
    assert tests == [{"phone": "+919811122233", "local": "9811122233", "name": "Test number", "since": None, "test": True}]
    assert _upload(client, "9811122233", rid="t1").status_code == 201
    assert _upload(client, "+919000000001", rid="real").status_code == 201
    summary = client.get("/api/v1/call-recordings/summary").json()
    assert summary["recordings"] == 1 and summary["tests"] == 1
    z = zipfile.ZipFile(io.BytesIO(client.get("/api/v1/call-recordings/export").content))
    assert len([n for n in z.namelist() if n.startswith("recordings/")]) == 1     # Sumit gets no tests
    # Not in the Excel copy either; and once the setting is cleared, the test phone is refused.
    from openpyxl import load_workbook
    ws = load_workbook(io.BytesIO(client.get("/api/v1/call-recordings/numbers.xlsx").content)).active
    assert "9811122233" not in [r[0] for r in ws.iter_rows(values_only=True)]
    monkeypatch.setenv("CALL_RECORDER_TEST_NUMBERS", "")
    assert _upload(client, "9811122233", rid="t2").status_code == 422


def test_cannot_invest_but_yes_to_esaf_is_still_qualified_and_marked_for_esaf():
    from src.services import applications
    base = {"coverage": SERVED, "education": "12", "can_invest": False}
    no = applications.qualify(WhatsAppConversation(phone="+919000000099", bot_step=bot.NOT_INVESTING, bot_data=base))
    assert no["verdict"] == "Not qualified" and not no["esaf"]
    yes = applications.qualify(WhatsAppConversation(phone="+919000000099", bot_step=bot.AWAIT_DOCS,
                                                    bot_data={**base, "esaf": True}))
    assert yes["strongly_qualified"] and not yes["not_qualified"] and yes["esaf"]
    assert yes["verdict"] == "Strongly qualified · ESAF"
    # Below 12th is still below 12th, ESAF or not.
    low = applications.qualify(WhatsAppConversation(phone="+919000000099", bot_step=bot.AWAIT_DOCS,
                                                    bot_data={**base, "education": "other", "esaf": True}))
    assert low["verdict"] == "Not qualified" and low["not_qualified_reasons"] == ["Below 12th"]
