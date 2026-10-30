"""
The inbox and the onboarding bot.

Inbound messages of every kind are recorded once, however often Meta
redelivers them. The bot walks someone from an "Interested" tap to uploaded
documents, says nothing it was not asked for, and stays quiet when paused.
The upload page accepts only real PDFs and images, and only on a live link.
"""
import re
import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base, get_db
from src.main import app
from src.models import (  # noqa: F401  (registers the tables on Base)
    AppSetting, AttentionTicket, ChatActivity, Location, OnboardingDocument, WhatsAppButtonClick, WhatsAppCampaign, WhatsAppTemplate,
    WhatsAppCampaignRecipient, WhatsAppConversation, WhatsAppMessage, WhatsAppReply,
)
from src.routers.auth import current_user
from src.routers import onboarding
from src.services import bot_messages, campaign_buttons, drive_uploads, inbox, onboarding_bot, pincode_coverage

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

PHONE = "+919000000001"
SERVED_PIN = "110001"

PDF = b"%PDF-1.4\n%test\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


class StubMeta:
    """Stands in for the Cloud API, and remembers what it was asked to send."""
    sent = []
    ok = True

    def _result(self):
        if StubMeta.ok:
            return True, f"wamid.{uuid.uuid4().hex}", "200", None, None
        return False, None, "400", "Meta API rejection: test", "131047"

    def send_text_message(self, to, body):
        StubMeta.sent.append(("text", to, body, None))
        return self._result()

    def send_button_message(self, to, body, buttons):
        StubMeta.sent.append(("buttons", to, body, buttons))
        return self._result()

    media = {}

    def download_media(self, media_id):
        if media_id in StubMeta.media:
            return StubMeta.media[media_id] + (None,)
        return None, None, "Media not found"

    def upload_media(self, path, kind):
        StubMeta.uploads.append((path, kind))
        return "media123"

    def send_media_message(self, to, kind, media_id, caption=None, filename=None):
        StubMeta.sent.append((kind, to, caption, {"media_id": media_id, "filename": filename}))
        return self._result()

    uploads = []

    def send_link_message(self, to, body, text, url):
        StubMeta.sent.append(("link", to, body, {"text": text, "url": url}))
        return self._result()

    def send_template_message(self, to, name, language="en_US", components=None):
        StubMeta.sent.append(("template", to, name, {"language": language}))
        return self._result()


@pytest.fixture(autouse=True)
def stub_meta(monkeypatch, tmp_path):
    StubMeta.sent = []
    StubMeta.ok = True
    StubMeta.media = {}
    monkeypatch.setattr(inbox, "MetaWhatsAppService", StubMeta)
    monkeypatch.setattr(inbox, "MEDIA_DIR", str(tmp_path / "media"))
    monkeypatch.setattr(onboarding, "DOCS_DIR", str(tmp_path))
    monkeypatch.setenv("WHATSAPP_BUSINESS_NUMBER", "+91 80000 00000")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://link.example.in")
    # Nothing in these tests may reach a real geocoder.
    monkeypatch.setattr(pincode_coverage, "_locate_or_none", lambda pin: None)
    # Nor a real Google Drive; the copy itself is tested on its own below.
    monkeypatch.setattr(drive_uploads, "save_in_background", lambda phone: None)
    # Personal guidance is offered for tomorrow whatever the hour the tests
    # run at; the tests of "today" set the hour themselves.
    monkeypatch.setattr(onboarding_bot, "GUIDANCE_TODAY_UNTIL", 0)


@pytest.fixture
def db():
    session = TestingSessionLocal()
    session.add(Location(location_id=uuid.uuid4().hex[:12], pincode=SERVED_PIN,
                         latitude=28.6328, longitude=77.2197, district="New Delhi", state="Delhi"))
    # The bot answers only people a campaign reached, so the test number
    # was sent one; the test that it ignores others uses another number.
    campaign_id = uuid.uuid4().hex
    session.add(WhatsAppCampaign(campaign_id=campaign_id, name="Delhi CSP", data_source_type="scraped",
                                 status="COMPLETED", total_contacts=50))
    session.add(WhatsAppCampaignRecipient(recipient_id=uuid.uuid4().hex, campaign_id=campaign_id,
                                          phone=PHONE, status="READ", provider_message_id="wamid.campaign.base"))
    session.commit()
    try:
        yield session
    finally:
        session.rollback()
        from src.models.inbox import FollowUp
        from src.models.agent_runs import AgentRun
        for model in (AgentRun, FollowUp, ChatActivity, AttentionTicket, OnboardingDocument, WhatsAppMessage, WhatsAppConversation, WhatsAppReply,
                      WhatsAppButtonClick, WhatsAppCampaignRecipient, WhatsAppCampaign,
                      WhatsAppTemplate, Location, AppSetting):
            session.query(model).delete()
        session.commit()
        session.close()


@pytest.fixture
def client(db):
    def override():
        yield db
    class Admin:
        email = "admin@eko.co.in"
        role = "admin"

    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = override
    app.dependency_overrides[current_user] = lambda: Admin()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


_seq = iter(range(10**6))


def inbound(db, kind="text", **fields):
    """Deliver one inbound message the way the webhook does, and let the bot answer it."""
    message = {"from": PHONE.lstrip("+"), "id": f"wamid.in{next(_seq)}",
               "timestamp": str(int(inbox.now().timestamp())), "type": kind, **fields}
    msg = inbox.record_inbound(db, message, "Ravi Kumar")
    db.commit()
    if msg is not None:
        conv = db.query(WhatsAppConversation).filter(WhatsAppConversation.phone == PHONE).one()
        onboarding_bot.handle(db, conv, msg)
        db.commit()
    return msg


def tap_campaign(db, text="Interested?", lang="en"):
    """Tap a campaign button and, when the bot asks, choose a language."""
    msg = inbound(db, "button", button={"text": text, "payload": text})
    c = db.query(WhatsAppConversation).filter(WhatsAppConversation.phone == PHONE).first()
    if lang and c is not None and c.bot_step == onboarding_bot.CHOOSE_LANG:
        tap(db, f"lang:{lang}")
    return msg


def tap(db, button_id):
    return inbound(db, "interactive", interactive={
        "type": "button_reply", "button_reply": {"id": button_id, "title": button_id}})


def qualify(db, education="12"):
    """Answer the education question that follows a served PIN."""
    tap(db, f"edu:{education}")


def say(db, text):
    return inbound(db, "text", text={"body": text})


def conv(db):
    c = db.query(WhatsAppConversation).filter(WhatsAppConversation.phone == PHONE).one()
    db.refresh(c)
    return c


# --- Recording -------------------------------------------------------------

def test_every_inbound_kind_is_recorded_once(db):
    message = {"from": "919000000001", "id": "wamid.X", "timestamp": "1760000000",
               "type": "image", "image": {"id": "m1", "caption": "my shop", "mime_type": "image/jpeg"}}
    first = inbox.record_inbound(db, message, "Ravi")
    again = inbox.record_inbound(db, message, "Ravi")
    db.commit()

    assert first is not None and again is None
    assert first.phone == PHONE
    assert first.body == "[Photo] my shop"
    c = conv(db)
    assert c.profile_name == "Ravi"
    assert c.last_inbound_at is not None


def test_status_updates_move_inbox_ticks_forward_only(db):
    inbound(db, "text", text={"body": "hello"})
    sent = inbox.send(db, PHONE, "Hi!", sent_by="me@eko.co.in")
    db.commit()
    pid = sent.provider_message_id

    assert inbox.apply_status(db, {"id": pid, "status": "read"})
    assert inbox.apply_status(db, {"id": pid, "status": "delivered"})
    assert sent.status == "READ"
    assert not inbox.apply_status(db, {"id": "wamid.campaign", "status": "read"})


# --- The bot ---------------------------------------------------------------

def test_full_onboarding_flow(db, client):
    tap_campaign(db)
    assert StubMeta.sent[-1][2] == onboarding_bot.ASK_PIN
    assert conv(db).bot_step == onboarding_bot.AWAIT_PIN

    say(db, "my pin is 110 001")
    kind, _to, body, buttons = StubMeta.sent[-1]
    assert (kind, body) == ("buttons", onboarding_bot.ASK_EDUCATION)
    assert [b["id"] for b in buttons] == ["edu:12", "edu:grad", "edu:other"]
    assert [b["title"] for b in buttons] == ["12th/Diploma", "Graduate/Post-Grad", "Other"]

    tap(db, "edu:grad")
    kind, _to, body, buttons = StubMeta.sent[-1]
    # One question covers the investment and the franchise.
    assert (kind, body) == ("buttons", onboarding_bot.ASK_INVEST)
    assert body.startswith("Are you able to invest ₹3–5 lakh (depending on your location) to set up a Franchise Business?")
    assert "A franchise business means" in body
    assert [b["id"] for b in buttons] == ["invest:yes", "invest:no"]
    assert conv(db).bot_data["education"] == "grad"

    tap(db, "invest:yes")
    kind, _to, body, _b = StubMeta.sent[-1]
    assert kind == "buttons" and "Aadhaar Card" in body

    tap(db, "docs:yes")
    kind, _to, body, link = StubMeta.sent[-1]
    assert kind == "link"
    c = conv(db)
    assert c.bot_step == onboarding_bot.AWAIT_UPLOAD
    assert link["url"] == f"https://link.example.in/onboard/{c.upload_token}"

    page = client.get(f"/onboard/{c.upload_token}")
    assert page.status_code == 200
    assert "Upload your documents" in page.text and '"state": "open"' in page.text

    # Not everything is in yet.
    files = f"/onboard/{c.upload_token}/files"
    assert client.post(files, data={"doc_type": "pan"}, files={"file": ("pan.pdf", PDF)}).status_code == 200
    assert client.post(f"/onboard/{c.upload_token}/submit").status_code == 400

    for d in onboarding_bot.DOCUMENTS:
        r = client.post(files, data={"doc_type": d["key"]}, files={"file": (f"{d['key']}.png", PNG)})
        assert r.status_code == 200, r.text
    # A re-upload replaces rather than adds.
    assert db.query(OnboardingDocument).count() == len(onboarding_bot.DOCUMENTS)

    assert client.post(f"/onboard/{c.upload_token}/submit").json() == {"status": "submitted"}
    assert StubMeta.sent[-1][2] == onboarding_bot.THANKS
    c = conv(db)
    assert c.bot_step == onboarding_bot.SUBMITTED and c.documents_submitted_at is not None

    # The inbox shows all of it, and the files can be read back.
    detail = client.get(f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}").json()
    assert detail["bot_step"] == onboarding_bot.SUBMITTED
    assert len(detail["document_files"]) == len(onboarding_bot.DOCUMENTS)
    doc_id = detail["document_files"][0]["document_id"]
    assert client.get(f"/api/v1/inbox/documents/{doc_id}").content in (PDF, PNG)


def test_a_pin_within_twenty_km_is_served(db, monkeypatch):
    # About 9 km from the served PIN.
    monkeypatch.setattr(pincode_coverage, "_locate_or_none", lambda pin: (28.55, 77.25))
    tap_campaign(db)
    say(db, "110017")
    assert StubMeta.sent[-1][2] == onboarding_bot.ASK_EDUCATION
    assert conv(db).bot_data["coverage"]["nearest_pincode"] == SERVED_PIN


def test_a_real_pin_further_away_carries_on_to_education(db, monkeypatch):
    # 2026-10-23: no longer the end of the journey; not qualified for SBI branch code instead.
    from src.services import applications
    monkeypatch.setattr(pincode_coverage, "_locate_or_none", lambda pin: (19.07, 72.87))  # Mumbai
    tap_campaign(db)
    say(db, "400001")
    assert StubMeta.sent[-1][2] == onboarding_bot.ASK_EDUCATION
    c = conv(db)
    assert c.bot_step == onboarding_bot.AWAIT_EDUCATION and c.bot_data["coverage"]["served"] is False
    q = applications.qualify(c)
    assert q["verdict"] == "Not qualified for SBI branch code" and q["other_proposal"]


def test_no_pin_three_times_hands_over_to_a_person(db):
    tap_campaign(db)
    say(db, "hello")
    assert StubMeta.sent[-1][2] == onboarding_bot.BAD_PIN
    say(db, "999")
    say(db, "nope")
    assert StubMeta.sent[-1][2] == onboarding_bot.HANDOVER_TEXT
    assert conv(db).bot_step == onboarding_bot.HANDOVER


def test_saying_no_to_investing_ends_politely(db):
    tap_campaign(db)
    say(db, SERVED_PIN)
    qualify(db)
    tap(db, "invest:no")
    assert StubMeta.sent[-1][2] == onboarding_bot.NOT_INVESTING_TEXT
    say(db, "ok thanks")  # answered politely, once
    assert StubMeta.sent[-1][2] == onboarding_bot.ACKNOWLEDGE
    count = len(StubMeta.sent)
    say(db, "bye")  # not again straight away
    assert len(StubMeta.sent) == count


def test_typed_yes_works_like_the_button(db):
    tap_campaign(db)
    say(db, SERVED_PIN)
    qualify(db)
    say(db, "Haan")
    assert "Aadhaar Card" in StubMeta.sent[-1][2]


def test_another_button_is_acknowledged_without_starting_the_flow(db):
    tap_campaign(db, "Not interested")
    assert [m[2] for m in StubMeta.sent] == [onboarding_bot.ACKNOWLEDGE]
    assert conv(db).bot_step is None


def test_a_pin_sent_out_of_the_blue_is_checked(db):
    say(db, SERVED_PIN)
    assert StubMeta.sent[-1][2] == onboarding_bot.ASK_EDUCATION


def test_someone_writing_first_is_greeted_and_can_start(db):
    say(db, "Hi")
    kind, _to, body, buttons = StubMeta.sent[-1]
    assert "Thank you for contacting Eko" in body
    assert [b["id"] for b in buttons] == [onboarding_bot.START_INTERESTED, onboarding_bot.START_WEBINAR]
    say(db, "hello")  # greeted once a day, not on every line
    assert len(StubMeta.sent) == 1
    tap(db, "start:interested")
    tap(db, "lang:en")
    assert StubMeta.sent[-1][2] == onboarding_bot.ASK_PIN


def test_someone_told_earlier_we_were_not_there_carries_on_when_they_write(db):
    tap_campaign(db)
    c = conv(db)
    c.bot_step, c.bot_data = onboarding_bot.NOT_SERVED, {**(c.bot_data or {}), "coverage": {"pincode": "400001", "served": False}}
    db.commit()
    say(db, "ok")
    assert StubMeta.sent[-1][2] == onboarding_bot.ASK_EDUCATION
    assert conv(db).bot_step == onboarding_bot.AWAIT_EDUCATION


def test_an_unclear_answer_gets_the_question_again(db):
    tap_campaign(db)
    say(db, SERVED_PIN)
    qualify(db)
    say(db, "hmm maybe")
    kind, _to, body, buttons = StubMeta.sent[-1]
    assert body == onboarding_bot.REMIND_INVEST and [b["id"] for b in buttons] == ["invest:yes", "invest:no"]


def test_an_amount_mid_question_is_not_read_as_a_pin(db):
    tap_campaign(db)
    say(db, SERVED_PIN)
    qualify(db)
    say(db, "haan, 500000 hai mere paas")
    assert conv(db).bot_step == onboarding_bot.AWAIT_INVEST


def test_replies_stop_after_a_few_it_did_not_understand(db, monkeypatch):
    # Lines the bot cannot act on are answered a few times, then left be.
    monkeypatch.setattr(onboarding_bot, "FALLBACK_GAP", timedelta(0))
    monkeypatch.setattr(onboarding_bot, "GREETING_GAP", timedelta(0))
    for i in range(6):
        say(db, f"ok ji ({i})")
    assert len(StubMeta.sent) == onboarding_bot.MAX_FALLBACK_STREAK


def test_a_repeating_auto_reply_is_greeted_once(db, monkeypatch):
    # Their bot answering ours must not go on for ever: one greeting, then quiet.
    monkeypatch.setattr(onboarding_bot, "FALLBACK_GAP", timedelta(0))
    monkeypatch.setattr(onboarding_bot, "GREETING_GAP", timedelta(0))
    for i in range(6):
        say(db, f"Thank you for contacting us! ({i})")
    assert len(StubMeta.sent) == 1


def test_a_paused_bot_says_nothing(db):
    tap_campaign(db)
    c = conv(db)
    c.bot_paused = True
    db.commit()
    count = len(StubMeta.sent)
    say(db, SERVED_PIN)
    assert len(StubMeta.sent) == count


def test_a_switched_off_bot_says_nothing(db):
    onboarding_bot.save_settings(db, False, ["Interested"])
    tap_campaign(db)
    assert StubMeta.sent == []


# --- Upload page -----------------------------------------------------------

def _link(db):
    tap_campaign(db)
    say(db, SERVED_PIN)
    qualify(db)
    tap(db, "invest:yes")
    tap(db, "docs:yes")
    return conv(db).upload_token


def test_only_real_pdfs_and_images_are_accepted(db, client):
    token = _link(db)
    r = client.post(f"/onboard/{token}/files", data={"doc_type": "pan"},
                    files={"file": ("pan.pdf", b"<html>not a pdf</html>")})
    assert r.status_code == 415
    r = client.post(f"/onboard/{token}/files", data={"doc_type": "passport"},
                    files={"file": ("x.pdf", PDF)})
    assert r.status_code == 400


def test_an_expired_or_unknown_link_is_refused(db, client):
    token = _link(db)
    c = conv(db)
    c.upload_token_expires_at = inbox.now() - timedelta(minutes=1)
    db.commit()
    assert '"state": "invalid"' in client.get(f"/onboard/{token}").text
    assert client.post(f"/onboard/{token}/files", data={"doc_type": "pan"},
                       files={"file": ("pan.pdf", PDF)}).status_code == 404
    assert '"state": "invalid"' in client.get("/onboard/not-a-token").text


# --- Replying from the inbox -----------------------------------------------

def test_reply_inside_the_window_is_sent(db, client):
    say(db, "Is anyone there?")
    r = client.post(f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}/messages",
                    json={"message": "  Yes, how can we help?  "})
    assert r.status_code == 200, r.text
    assert StubMeta.sent[-1][:3] == ("text", PHONE, "Yes, how can we help?")

    listing = client.get("/api/v1/inbox/conversations").json()
    assert listing[0]["phone"] == PHONE and listing[0]["last_direction"] == "OUT"


def test_reply_refused_once_the_window_has_closed(db, client):
    say(db, "hello")
    c = conv(db)
    c.last_inbound_at = inbox.now() - timedelta(hours=25)
    db.commit()
    StubMeta.sent = []  # the bot's greeting to "hello" is not what is tested here
    r = client.post(f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}/messages", json={"message": "Hi"})
    assert r.status_code == 409
    assert StubMeta.sent == []


def test_unread_counts_clear_when_read(db, client):
    say(db, "one")
    say(db, "two")
    assert client.get("/api/v1/inbox/conversations").json()[0]["unread"] == 2
    client.post(f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}/read")
    assert client.get("/api/v1/inbox/conversations").json()[0]["unread"] == 0


def test_pin_extraction():
    assert pincode_coverage.extract_pincode("PIN 560 034 please") == "560034"
    assert pincode_coverage.extract_pincode("call 9876543210") is None
    assert pincode_coverage.extract_pincode("012345") is None


# --- Google Drive ------------------------------------------------------------

class FakeResponse:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


class FakeDrive:
    """Answers the two Drive calls made: create a folder, upload a file."""
    def __init__(self, fail_uploads=False):
        self.folders, self.uploads, self.fail_uploads = [], [], fail_uploads

    def post(self, url, params=None, json=None, data=None, headers=None, timeout=None):
        assert params["supportsAllDrives"] == "true"
        if url == drive_uploads.FILES_URL:
            self.folders.append(json)
            return FakeResponse(200, {"id": "folder1", "webViewLink": "https://drive/folder1"})
        if self.fail_uploads:
            return FakeResponse(403, {"error": {"errors": [{"reason": "storageQuotaExceeded"}],
                                                "message": "quota"}})
        self.uploads.append(data)
        n = len(self.uploads)
        return FakeResponse(200, {"id": f"file{n}", "webViewLink": f"https://drive/file{n}"})


def _submitted(db, client):
    token = _link(db)
    for d in onboarding_bot.DOCUMENTS:
        client.post(f"/onboard/{token}/files", data={"doc_type": d["key"]},
                    files={"file": (f"{d['key']}.pdf", PDF)})
    client.post(f"/onboard/{token}/submit")
    return conv(db)


def test_documents_are_copied_to_drive_and_then_removed_locally(db, client, monkeypatch):
    c = _submitted(db, client)
    fake = FakeDrive()
    monkeypatch.setenv("GOOGLE_DRIVE_FOLDER_ID", "parent")
    monkeypatch.setenv("GOOGLE_CREDENTIALS_BASE64", "x")
    monkeypatch.setattr(drive_uploads, "_session", lambda: fake)

    assert drive_uploads.save_conversation(db, c) == len(onboarding_bot.DOCUMENTS)
    assert fake.folders[0]["parents"] == ["parent"]
    assert "Ravi Kumar" in fake.folders[0]["name"] and PHONE in fake.folders[0]["name"]

    docs = db.query(OnboardingDocument).all()
    assert all(d.drive_url and not __import__("os").path.exists(d.stored_path) for d in docs)
    # The inbox now sends people to Drive for the file.
    r = client.get(f"/api/v1/inbox/documents/{docs[0].document_id}", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith("https://drive/")
    # Running again copies nothing twice.
    assert drive_uploads.save_conversation(db, c) == 0


def test_a_failed_drive_copy_keeps_the_file_and_says_why(db, client, monkeypatch):
    c = _submitted(db, client)
    monkeypatch.setenv("GOOGLE_DRIVE_FOLDER_ID", "parent")
    monkeypatch.setenv("GOOGLE_CREDENTIALS_BASE64", "x")
    monkeypatch.setattr(drive_uploads, "_session", lambda: FakeDrive(fail_uploads=True))

    assert drive_uploads.save_conversation(db, c) == 0
    doc = db.query(OnboardingDocument).first()
    assert doc.drive_file_id is None and "shared drive" in doc.drive_error
    assert __import__("os").path.exists(doc.stored_path)
    assert client.get(f"/api/v1/inbox/documents/{doc.document_id}").content == PDF


def test_backfill_skips_a_tap_the_webhook_already_recorded(db):
    # The live webhook stores the tap under a new id, and the old leads
    # table keeps its own row for the same tap: copying it again would
    # break the unique Meta id and stop the whole backfill.
    campaign_id, recipient_id = uuid.uuid4().hex, uuid.uuid4().hex
    db.add(WhatsAppCampaign(campaign_id=campaign_id, name="T", data_source_type="scraped",
                            status="COMPLETED", total_contacts=1))
    db.add(WhatsAppCampaignRecipient(recipient_id=recipient_id, campaign_id=campaign_id,
                                     phone=PHONE, status="READ", provider_message_id="wamid.camp"))
    db.add(WhatsAppButtonClick(click_id=uuid.uuid4().hex, campaign_id=campaign_id,
                               recipient_id=recipient_id, button_text="Interested",
                               provider_message_id="wamid.tap1", clicked_at=inbox.now()))
    db.commit()
    inbox.record_inbound(db, {"from": PHONE.lstrip("+"), "id": "wamid.tap1", "type": "button",
                              "button": {"text": "Interested"}}, None)
    db.commit()

    assert inbox.backfill_from_leads(db) == 0
    assert db.query(WhatsAppMessage).filter(WhatsAppMessage.provider_message_id == "wamid.tap1").count() == 1


# --- Photos, videos and documents people send --------------------------------

def _photo(db, media_id="m1", caption="my shop"):
    msg = inbox.record_inbound(db, {"from": PHONE.lstrip("+"), "id": f"wamid.{media_id}", "type": "image",
                                    "image": {"id": media_id, "mime_type": "image/jpeg", "caption": caption}},
                               "Ravi")
    db.commit()
    return msg


def test_a_photo_is_fetched_and_shown_in_the_thread(db, client):
    StubMeta.media["m1"] = (PNG, "image/png")
    msg = _photo(db)
    inbox.fetch_media(msg)
    db.commit()

    detail = client.get(f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}").json()
    shown = next(m for m in detail["messages"] if m["id"] == msg.message_id)
    # The page learns the file is there, never where it is on the server.
    assert shown["payload"]["available"] is True and "stored" not in shown["payload"]

    r = client.get(f"/api/v1/inbox/media/{msg.message_id}")
    assert r.status_code == 200 and r.content == PNG
    assert r.headers["content-type"] == "image/png"
    assert r.headers["content-disposition"].startswith("inline")


def test_a_file_not_fetched_on_arrival_is_fetched_when_opened(db, client):
    msg = _photo(db, "m2")
    assert inbox.fetch_media(msg) == "Media not found"
    db.commit()
    StubMeta.media["m2"] = (PNG, "image/jpeg")

    r = client.get(f"/api/v1/inbox/media/{msg.message_id}")
    assert r.status_code == 200 and r.content == PNG


def test_an_unknown_file_type_is_only_ever_downloaded(db, client):
    # (A web page or an archive is blocked outright; see the malware test.)
    StubMeta.media["d1"] = (b"<b>notes</b>", "application/x-custom-notes")
    msg = inbox.record_inbound(db, {"from": PHONE.lstrip("+"), "id": "wamid.d1", "type": "document",
                                    "document": {"id": "d1", "filename": "notes.xyz", "mime_type": "application/x-custom-notes"}},
                               None)
    db.commit()
    r = client.get(f"/api/v1/inbox/media/{msg.message_id}")
    assert r.status_code == 200
    assert r.headers["content-disposition"].startswith("attachment")
    assert r.headers["content-type"] == "application/octet-stream"


# --- Only people an AutoGMap campaign reached --------------------------------

OTHER = "+919000000002"


def test_the_bot_leaves_people_from_elsewhere_alone(db, client):
    # Someone writing to the shared number who was never sent our campaign.
    msg = inbox.record_inbound(db, {"from": OTHER.lstrip("+"), "id": "wamid.other1", "type": "button",
                                    "button": {"text": "Interested"}}, "Someone else")
    db.commit()
    onboarding_bot.handle(db, inbox.conversation(db, OTHER), msg)
    db.commit()
    assert StubMeta.sent == []

    # Still shown in the inbox, just not marked as ours.
    listing = {c["phone"]: c for c in client.get("/api/v1/inbox/conversations").json()}
    assert listing[OTHER]["from_campaign"] is False


def test_people_a_campaign_reached_are_marked_from_autogmap(db, client):
    say(db, "hello")
    listing = {c["phone"]: c for c in client.get("/api/v1/inbox/conversations").json()}
    assert listing[PHONE]["from_campaign"] is True
    assert client.get(f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}").json()["from_campaign"] is True


def test_only_the_required_documents_hold_up_submitting(db, client):
    token = _link(db)
    for d in onboarding_bot.REQUIRED_DOCUMENTS[:-1]:
        client.post(f"/onboard/{token}/files", data={"doc_type": d["key"]}, files={"file": ("a.pdf", PDF)})
    r = client.post(f"/onboard/{token}/submit")
    assert r.status_code == 400 and onboarding_bot.REQUIRED_DOCUMENTS[-1]["label"] in r.json()["detail"]

    last = onboarding_bot.REQUIRED_DOCUMENTS[-1]
    client.post(f"/onboard/{token}/files", data={"doc_type": last["key"]}, files={"file": ("a.pdf", PDF)})
    assert client.post(f"/onboard/{token}/submit").json() == {"status": "submitted"}


# --- Language, and the webinar ----------------------------------------------

def _punjabi_campaign(db):
    """Send PHONE a campaign whose template is written in Punjabi."""
    template_id, campaign_id = uuid.uuid4().hex, uuid.uuid4().hex
    db.add(WhatsAppTemplate(template_id=template_id, name="Punjab", body="ਸਤ ਸ੍ਰੀ ਅਕਾਲ {{1}}",
                            language_code="pa", buttons=campaign_buttons.quick_replies("pa")))
    db.add(WhatsAppCampaign(campaign_id=campaign_id, name="Punjab", template_id=template_id,
                            data_source_type="scraped", status="COMPLETED", total_contacts=1))
    db.add(WhatsAppCampaignRecipient(recipient_id=uuid.uuid4().hex, campaign_id=campaign_id,
                                     phone=PHONE, status="READ", provider_message_id="wamid.punjab"))
    db.commit()


def test_interested_first_asks_the_language(db):
    tap_campaign(db, lang=None)
    kind, _to, body, buttons = StubMeta.sent[-1]
    assert kind == "buttons" and [b["id"] for b in buttons] == ["lang:en", "lang:hi"]
    assert conv(db).bot_step == onboarding_bot.CHOOSE_LANG


def test_the_campaigns_own_language_is_offered_and_used(db):
    _punjabi_campaign(db)
    tap_campaign(db, lang=None)
    assert [b["id"] for b in StubMeta.sent[-1][3]] == ["lang:en", "lang:hi", "lang:pa"]
    tap(db, "lang:pa")
    assert StubMeta.sent[-1][2] == bot_messages.MESSAGES["pa"]["ask_pin"]
    say(db, SERVED_PIN)
    kind, _to, body, buttons = StubMeta.sent[-1]
    assert body == bot_messages.MESSAGES["pa"]["ask_education"]
    assert [b["title"] for b in buttons] == ["12ਵੀਂ/ਡਿਪਲੋਮਾ", "ਗ੍ਰੈਜੂਏਟ/ਪੀਜੀ", "ਹੋਰ"]
    qualify(db)
    kind, _to, body, buttons = StubMeta.sent[-1]
    assert body == bot_messages.MESSAGES["pa"]["ask_invest"]
    assert [b["title"] for b in buttons] == ["ਹਾਂ", "ਨਹੀਂ"]


def test_a_typed_language_name_counts(db):
    tap_campaign(db, lang=None)
    say(db, "Hindi")
    assert StubMeta.sent[-1][2] == bot_messages.MESSAGES["hi"]["ask_pin"]


@pytest.fixture
def told(monkeypatch):
    from src.services import notifier
    calls = []
    monkeypatch.setattr(notifier, "notify_webinar", lambda to, details: calls.append(details))
    return calls





def test_every_language_has_every_message_and_short_buttons():
    keys = set(bot_messages.MESSAGES["en"])
    for lang, msgs in bot_messages.MESSAGES.items():
        assert set(msgs) == keys, lang
        for k in ("yes", "no", "link_button"):
            assert len(msgs[k]) <= 20, (lang, k)
    for lang, label in campaign_buttons.WEBINAR.items():
        # A template's button may be 25 characters; one the bot sends, 20.
        assert len(label) <= 25 and campaign_buttons.is_webinar(label)
        title = campaign_buttons.webinar_title(lang)
        assert len(title) <= 20 and title.split()[0] == label.split()[0]
    # Buttons on templates approved before the rename still start the flow.
    for label in campaign_buttons.OLD_WEBINAR.values():
        assert campaign_buttons.is_webinar(label)
    assert campaign_buttons.is_webinar("પર્સનલ ગાઇડન્સ જોઈએ")
    assert not campaign_buttons.is_webinar("Interested")


def test_a_new_campaign_in_another_language_asks_again(db):
    # Chose Hindi while the newest campaign was English...
    tap_campaign(db, text=campaign_buttons.WEBINAR["en"], lang="hi")
    # ...then a Punjabi campaign arrives, and its button is tapped.
    _punjabi_campaign(db)
    tap_campaign(db, text=campaign_buttons.WEBINAR["pa"], lang=None)
    kind, _to, body, buttons = StubMeta.sent[-1]
    assert [b["id"] for b in buttons] == ["lang:en", "lang:hi", "lang:pa"]
    tap(db, "lang:pa")
    assert StubMeta.sent[-1][2] == bot_messages.MESSAGES["pa"]["guidance_open"]


def test_one_stray_letter_does_not_change_a_templates_language():
    class T:
        language_code = "en_US"
        body = "નમસ્તે, આ ગુજરાતી સંદેશ છે ਰ"
    assert onboarding_bot.language_of_template(T()) == "gu"
    T.language_code = "gu"
    assert onboarding_bot.language_of_template(T()) == "gu"


# --- Education and franchise, before the investment question ----------------

def test_below_12th_is_told_politely_and_the_flow_ends(db):
    tap_campaign(db)
    say(db, SERVED_PIN)
    tap(db, "edu:other")
    assert StubMeta.sent[-1][2] == onboarding_bot.NOT_ELIGIBLE_TEXT
    assert "12th" in StubMeta.sent[-1][2]
    c = conv(db)
    assert c.bot_step == onboarding_bot.NOT_ELIGIBLE and c.bot_data["education"] == "other"
    count = len(StubMeta.sent)
    tap(db, "invest:yes")  # an old button tapped later does not slip past
    assert conv(db).bot_step == onboarding_bot.NOT_ELIGIBLE
    assert all("Aadhaar" not in m[2] for m in StubMeta.sent[count:])


def test_someone_left_at_the_old_franchise_step_still_goes_on(db):
    tap_campaign(db)
    say(db, SERVED_PIN)
    c = conv(db)
    c.bot_step = onboarding_bot.AWAIT_FRANCHISE  # asked before the questions were joined
    db.commit()
    tap(db, "franchise:no")
    assert StubMeta.sent[-1][2] == onboarding_bot.ASK_INVEST
    assert conv(db).bot_data["franchise"] is False


def test_typed_education_counts(db):
    tap_campaign(db)
    say(db, SERVED_PIN)
    say(db, "Graduate")
    assert StubMeta.sent[-1][2] == onboarding_bot.ASK_INVEST


def test_an_unclear_education_answer_gets_the_buttons_again(db):
    tap_campaign(db)
    say(db, SERVED_PIN)
    say(db, "not sure")
    kind, _to, body, buttons = StubMeta.sent[-1]
    assert body == onboarding_bot.ASK_EDUCATION
    assert [b["id"] for b in buttons] == ["edu:12", "edu:grad", "edu:other"]


def test_every_language_has_short_education_buttons():
    for lang, msgs in bot_messages.MESSAGES.items():
        for k in ("edu_12", "edu_grad", "edu_other"):
            assert len(msgs[k]) <= 20, (lang, k, msgs[k])


# --- Questions the bot cannot answer, for a person ---------------------------

def test_a_question_marks_the_conversation_and_is_thanked(db):
    tap_campaign(db)
    say(db, SERVED_PIN)
    # Not in Eko's FAQ ("Isme kitna kamaunga?" now is: the bot answers that itself).
    say(db, "Kya aap Sunday ko bhi baat karte ho?")
    body = StubMeta.sent[-1][2]
    assert body.startswith(bot_messages.MESSAGES["en"]["question_ack"])
    assert onboarding_bot.ASK_EDUCATION in body  # and the question it left is asked again
    c = conv(db)
    assert c.needs_attention and c.attention_reason == "Kya aap Sunday ko bhi baat karte ho?"
    assert c.bot_step == onboarding_bot.AWAIT_EDUCATION


def test_a_question_at_the_pin_step_is_not_a_failed_attempt(db):
    tap_campaign(db)
    say(db, "PIN code kya hota hai?")
    c = conv(db)
    assert c.needs_attention and c.bot_step == onboarding_bot.AWAIT_PIN
    assert c.bot_data.get("pin_attempts", 0) == 0


def test_plain_replies_do_not_need_attention(db):
    tap_campaign(db)
    say(db, SERVED_PIN)
    say(db, "ok")
    assert not conv(db).needs_attention


def test_a_question_while_the_bot_is_paused_still_needs_attention(db):
    say(db, "hello")
    c = conv(db)
    c.bot_paused = True
    db.commit()
    count = len(StubMeta.sent)
    say(db, "When will someone call me?")
    assert conv(db).needs_attention and len(StubMeta.sent) == count


def test_people_from_elsewhere_are_never_marked(db):
    msg = inbox.record_inbound(db, {"from": "919000000002", "id": "wamid.q2", "type": "text",
                                    "text": {"body": "What is this?"}}, None)
    db.commit()
    other = inbox.conversation(db, "+919000000002")
    onboarding_bot.handle(db, other, msg)
    assert not other.needs_attention


def test_three_failed_pins_need_a_person(db):
    tap_campaign(db)
    for text in ("hello", "999", "nope"):
        say(db, text)
    c = conv(db)
    assert c.bot_step == onboarding_bot.HANDOVER and c.needs_attention


def test_attention_can_be_set_by_hand_and_only_resolved_by_hand(db, client):
    say(db, "hello")
    path = f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}/attention"
    assert client.post(path, json={"needed": True}).status_code == 200
    item = client.get("/api/v1/inbox/conversations").json()[0]
    assert item["needs_attention"] and "admin@eko.co.in" in item["attention_reason"]
    # A reply alone does not clear it.
    client.post(f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}/messages", json={"message": "Hi!"})
    assert conv(db).needs_attention
    assert client.post(path, json={"needed": False}).status_code == 200
    c = conv(db)
    assert not c.needs_attention and c.attention_resolved_by == "admin@eko.co.in"


def test_attention_cannot_be_set_on_someone_from_elsewhere(db, client):
    inbox.record_inbound(db, {"from": "919000000002", "id": "wamid.q3", "type": "text",
                              "text": {"body": "hi"}}, None)
    db.commit()
    r = client.post("/api/v1/inbox/conversations/919000000002/attention", json={"needed": True})
    assert r.status_code == 409


# --- Nudges, an hour after someone stops answering ---------------------------

from src.services import nudges  # noqa: E402


def _hours_later(h):
    return inbox.now() + timedelta(hours=h)


def test_someone_quiet_for_an_hour_is_nudged_once_with_the_same_question(db):
    tap_campaign(db)
    say(db, SERVED_PIN)          # the bot asks about education, and they go quiet
    count = len(StubMeta.sent)
    assert nudges.tick(db, _hours_later(0.5)) == 0, "not before an hour"
    assert nudges.tick(db, _hours_later(1.1)) == 1
    kind, _to, body, buttons = StubMeta.sent[-1]
    assert body.startswith(bot_messages.MESSAGES["en"]["nudge"])
    assert onboarding_bot.ASK_EDUCATION in body
    assert [b["id"] for b in buttons] == ["edu:12", "edu:grad", "edu:other"]
    assert len(StubMeta.sent) == count + 1
    assert nudges.tick(db, _hours_later(3)) == 0, "one reminder per pause"


def _age(db, hours):
    """Move the whole conversation this many hours into the past."""
    for m in db.query(WhatsAppMessage).filter(WhatsAppMessage.phone == PHONE).all():
        m.created_at = inbox.aware(m.created_at) - timedelta(hours=hours)
    c = conv(db)
    c.last_inbound_at = inbox.aware(c.last_inbound_at) - timedelta(hours=hours)
    db.commit()


def test_a_reply_and_a_new_pause_gets_a_new_nudge(db):
    tap_campaign(db)
    say(db, SERVED_PIN)
    _age(db, 1.1)
    assert nudges.tick(db) == 1
    tap(db, "edu:12")            # they come back, then go quiet again
    assert nudges.tick(db) == 0
    assert nudges.tick(db, _hours_later(1.1)) == 1
    assert onboarding_bot.ASK_INVEST in StubMeta.sent[-1][2]


def test_the_nudge_is_in_their_language(db):
    tap_campaign(db, lang="hi")
    assert nudges.tick(db, _hours_later(1.1)) == 1
    body = StubMeta.sent[-1][2]
    assert body.startswith(bot_messages.MESSAGES["hi"]["nudge"])
    assert bot_messages.MESSAGES["hi"]["bad_pin"] in body


def test_no_nudge_when_waiting_for_a_person_or_after_the_window(db):
    tap_campaign(db)
    c = conv(db)
    c.needs_attention = True
    db.commit()
    assert nudges.tick(db, _hours_later(1.1)) == 0
    c.needs_attention = False
    db.commit()
    assert nudges.tick(db, _hours_later(23.95)) == 0, "too close to the 24-hour limit"


def test_no_nudge_once_the_flow_has_ended(db):
    tap_campaign(db)
    say(db, SERVED_PIN)
    tap(db, "edu:other")         # not eligible: nothing left to ask
    assert nudges.tick(db, _hours_later(2)) == 0


# --- Sending files from the inbox ---------------------------------------------

def test_a_photo_is_sent_and_shown_in_the_thread(db, client):
    say(db, "hello")
    r = client.post(f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}/media",
                    files={"file": ("shop.png", PNG, "image/png")}, data={"caption": "Our kiosk 😊"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["kind"] == "image" and out["payload"]["available"] and "stored" not in out["payload"]
    assert StubMeta.sent[-1][:3] == ("image", PHONE, "Our kiosk 😊")
    # The thread can show it back.
    got = client.get(f"/api/v1/inbox/media/{out['id']}")
    assert got.status_code == 200 and got.content == PNG


def test_an_unknown_type_goes_as_a_document_and_size_is_checked(db, client):
    say(db, "hello")
    path = f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}/media"
    r = client.post(path, files={"file": ("list.xlsx", b"PK" + bytes([3, 4]) + b"data", "application/vnd.ms-excel")})
    assert r.status_code == 200 and r.json()["kind"] == "document"
    assert StubMeta.sent[-1][3]["filename"] == "list.xlsx"
    big = bytes([0xFF, 0xD8, 0xFF]) + b"0" * (5 * 1024 * 1024 + 10)
    assert client.post(path, files={"file": ("big.jpg", big, "image/jpeg")}).status_code == 413


def test_no_file_after_the_window_has_closed(db, client):
    say(db, "hello")
    c = conv(db)
    c.last_inbound_at = inbox.now() - timedelta(hours=25)
    db.commit()
    r = client.post(f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}/media",
                    files={"file": ("a.png", PNG, "image/png")})
    assert r.status_code == 409


# --- Voice notes ---------------------------------------------------------------

@pytest.fixture
def heard(monkeypatch):
    """Whisper stands in: what it will hear, and in which language."""
    from src.services import transcribe
    said = {"text": "", "language": "hi", "probability": 0.95}
    monkeypatch.setattr(transcribe, "transcribe", lambda path, fallback_language=None: dict(said))
    return said


def _voice(db, media_id="v1"):
    StubMeta.media[media_id] = (b"OggS" + b"0" * 40, "audio/ogg")
    msg = inbox.record_inbound(db, {"from": PHONE.lstrip("+"), "id": f"wamid.{media_id}", "type": "audio",
                                    "audio": {"id": media_id, "mime_type": "audio/ogg; codecs=opus"}}, None)
    db.commit()
    c = conv(db)
    onboarding_bot.transcribe_voice(db, c, msg)
    onboarding_bot.handle(db, c, msg)
    db.commit()
    return msg


def test_a_spoken_pin_is_understood_and_answered_in_the_language_spoken(db, heard):
    tap_campaign(db)                              # English chosen
    heard.update(text="मेरा पिन कोड 110001 है", language="hi")
    msg = _voice(db)
    assert msg.payload["transcript"] == "मेरा पिन कोड 110001 है"
    assert StubMeta.sent[-1][2] == bot_messages.MESSAGES["hi"]["ask_education"]
    assert conv(db).bot_data["lang"] == "hi"


def test_a_spoken_question_is_marked_for_a_person(db, heard):
    tap_campaign(db)
    # Not in Eko's FAQ ("इसमें कितना पैसा लगेगा" now is: the bot answers it, and a person still checks).
    heard.update(text="मेरे घर का पता बदलना है, क्या करना होगा", language="hi")
    _voice(db)
    c = conv(db)
    assert c.needs_attention and "पता" in c.attention_reason
    assert StubMeta.sent[-1][2].startswith(bot_messages.MESSAGES["hi"]["question_ack"])


def test_a_voice_note_that_cannot_be_transcribed_is_kept(db, monkeypatch):
    from src.services import transcribe

    def broken(path, fallback_language=None):
        raise RuntimeError("model unavailable")
    monkeypatch.setattr(transcribe, "transcribe", broken)
    tap_campaign(db)
    msg = _voice(db, "v2")
    assert "model unavailable" in msg.payload["transcript_error"]
    assert msg.payload.get("stored")              # still there to listen to


def test_a_voice_note_the_bot_cannot_act_on_always_needs_a_person(db, heard):
    tap_campaign(db)
    say(db, SERVED_PIN)                  # waiting for education
    heard.update(text="Mam nadzieje", language="hi")   # a wrong transcript
    _voice(db, "v9")
    c = conv(db)
    assert c.needs_attention and c.attention_reason.startswith("Voice note")
    assert StubMeta.sent[-1][2].startswith(bot_messages.MESSAGES["hi"]["question_ack"])


def test_wanting_to_ask_counts_as_a_question(db):
    tap_campaign(db)
    say(db, SERVED_PIN)
    say(db, "ok")                        # a plain reply, paced
    say(db, "Mujhe kuch puchna hai")     # straight after: still answered and marked
    assert conv(db).needs_attention
    assert StubMeta.sent[-1][2].startswith(bot_messages.MESSAGES["en"]["question_ack"])


def test_the_language_is_chosen_among_the_bots_own():
    from src.services import transcribe

    class Model:
        def detect_language(self, audio):
            return "pl", 0.46, [("pl", 0.46), ("ru", 0.13), ("en", 0.05), ("hi", 0.04), ("ur", 0.03)]
    # Polish and Russian are not options; Urdu counts as Hindi, which then leads.
    assert transcribe.choose_language(Model(), None)[0] == "hi"
    # The conversation's own language is preferred when the scores are close.
    assert transcribe.choose_language(Model(), None, fallback_language="en")[0] == "en"


def test_questions_are_answered_past_the_few_in_a_row_limit(db, monkeypatch):
    # Someone whose documents are in is past every question, so all they say
    # is "not understood"; their questions must still be answered.
    monkeypatch.setattr(onboarding_bot, "FALLBACK_GAP", timedelta(0))
    tap_campaign(db)
    for i in range(onboarding_bot.MAX_FALLBACK_STREAK):
        say(db, f"ok {i}")
    sent = len(StubMeta.sent)
    say(db, "Mere kuch sawal hain")
    assert len(StubMeta.sent) == sent + 1
    assert StubMeta.sent[-1][2].startswith(bot_messages.MESSAGES["en"]["question_ack"])


def test_a_run_of_replies_is_forgotten_after_a_while(db, monkeypatch):
    monkeypatch.setattr(onboarding_bot, "FALLBACK_GAP", timedelta(0))
    tap_campaign(db)
    for i in range(onboarding_bot.MAX_FALLBACK_STREAK + 1):
        say(db, f"ok {i}")
    c = conv(db)
    earlier = inbox.now() - onboarding_bot.STREAK_RESET - timedelta(minutes=1)
    c.bot_data = {**c.bot_data, "fallback_at": earlier.isoformat()}
    db.commit()
    sent = len(StubMeta.sent)
    say(db, "ok again")
    assert len(StubMeta.sent) == sent + 1


def test_a_hindi_note_is_written_out_by_the_hindi_model(monkeypatch):
    from src.services import transcribe

    used = []

    class Model:
        def __init__(self, name):
            self.name = name

        def detect_language(self, audio):
            return "hi", 0.9, [("hi", 0.9)]

        def transcribe(self, audio, **kw):
            used.append(self.name)
            return [type("S", (), {"text": "मुझे सवाल पूछना है"})()], None

    monkeypatch.setattr(transcribe, "_load", lambda name=None: Model(name or transcribe.MODEL))
    monkeypatch.setattr(transcribe, "_audio", lambda path: None)
    assert transcribe.transcribe("x.ogg")["text"] == "मुझे सवाल पूछना है"
    assert used == [transcribe.HINDI_MODEL]


def test_a_draft_with_the_old_webinar_button_is_submitted_with_the_new_one():
    from types import SimpleNamespace

    from src.services import whatsapp_service

    draft = SimpleNamespace(
        language_code="gu", header_type=None, header_content=None, body="Hello", footer=None,
        buttons=[{"type": "QUICK_REPLY", "text": "Interested"},
                 {"type": "QUICK_REPLY", "text": campaign_buttons.OLD_WEBINAR["gu"]}])
    components = whatsapp_service.build_meta_components(draft)
    buttons = next(c for c in components if c["type"] == "BUTTONS")["buttons"]
    assert [b["text"] for b in buttons] == ["Interested", "પર્સનલ ગાઇડન્સ જોઈએ"]


def _tapped_at(monkeypatch, hour, minute):
    """Make it this time of day in India when the button is tapped."""
    from datetime import datetime, timezone

    at = datetime(2026, 10, 14, hour, minute, tzinfo=onboarding_bot.IST).astimezone(timezone.utc)
    monkeypatch.setattr(onboarding_bot, "GUIDANCE_TODAY_UNTIL", 18)
    monkeypatch.setattr(inbox, "now", lambda: at)


def test_a_new_education_answer_after_not_eligible_carries_on(db):
    tap_campaign(db)
    say(db, SERVED_PIN)
    qualify(db, "other")
    assert conv(db).bot_step == onboarding_bot.NOT_ELIGIBLE
    qualify(db, "12")                    # tapped the right one after all
    assert conv(db).bot_step == onboarding_bot.AWAIT_INVEST
    assert StubMeta.sent[-1][2] == bot_messages.MESSAGES["en"]["ask_invest"]


def test_typing_12_after_not_eligible_carries_on(db):
    tap_campaign(db)
    say(db, SERVED_PIN)
    qualify(db, "other")
    say(db, "12")
    assert conv(db).bot_step == onboarding_bot.AWAIT_INVEST


def test_the_investment_question_explains_a_franchise_business_and_so_does_its_nudge(db):
    for lang, msgs in bot_messages.MESSAGES.items():
        assert msgs["ask_invest"].split("\n\n")[1] == bot_messages._FRANCHISE_MEANING[lang]
    assert "background" not in bot_messages.MESSAGES["en"]["ask_invest"]
    tap_campaign(db)
    say(db, SERVED_PIN)
    qualify(db)                  # asked about investing, and they go quiet
    assert nudges.tick(db, _hours_later(1.1)) == 1
    body = StubMeta.sent[-1][2]
    assert "A franchise business means running your own outlet" in body
    assert bot_messages.MESSAGES["en"]["ask_invest"] in body


def test_a_question_the_faq_answers_is_answered_and_the_question_asked_again(db):
    tap_campaign(db)
    say(db, SERVED_PIN)
    qualify(db)                                  # now asked about investing
    say(db, "Kitna invest karna hoga?")
    body = StubMeta.sent[-1][2]
    assert body.startswith("₹3–5 lakh, depending")                   # in English, as chosen
    assert bot_messages.MESSAGES["en"]["ask_invest"] in body     # and the question follows
    c = conv(db)
    assert c.bot_step == onboarding_bot.AWAIT_INVEST
    assert not c.needs_attention, "an answered question needs nobody"
    assert c.bot_data["faq_answered"] == ["investment"]


def test_the_faq_answer_is_in_the_persons_language(db):
    tap_campaign(db, lang="hi")
    say(db, "क्या फिक्स सैलरी मिलेगी?")
    assert StubMeta.sent[-1][2].startswith("नहीं। यह नौकरी नहीं, बिज़नेस है।")


def test_a_question_the_faq_does_not_answer_still_goes_to_a_person(db):
    tap_campaign(db)
    say(db, "Mere ghar ka pata badalna hai, kya karna hoga?")
    c = conv(db)
    assert c.needs_attention
    assert StubMeta.sent[-1][2].startswith(bot_messages.MESSAGES["en"]["question_ack"])


def test_a_voice_note_answered_from_the_faq_is_still_checked_by_a_person(db, heard):
    tap_campaign(db)
    heard.update(text="apply karne ki fees kitni hai", language="hi")
    _voice(db, "vf")
    # Heard as Hindi in Latin letters, so answered in Hinglish.
    assert StubMeta.sent[-1][2].startswith("Apply karna free hai.")
    assert conv(db).needs_attention


def test_what_the_5_lakh_is_for_comes_before_the_investment_question(db):
    tap_campaign(db)
    say(db, SERVED_PIN)
    count = len(StubMeta.sent)
    qualify(db)
    (_k1, _t1, explained, b1), (_k2, _t2, question, b2) = StubMeta.sent[count:count + 2]
    assert explained == bot_messages.MESSAGES["en"]["invest_explained"] and not b1
    assert explained.startswith("💼 *How ₹3–5 lakh (depending on your location) is used*")
    assert "e-wallet" in explained and "₹1–1.5 lakh" in explained and "In the evening, the amount you transacted" in explained and "Some of the money stays with you" in explained and "mini branch" in explained
    assert "security deposit" not in explained
    assert "₹3–5 lakh (depending on your location)" in question
    assert question == bot_messages.MESSAGES["en"]["ask_invest"]
    assert [b["id"] for b in b2] == ["invest:yes", "invest:no"]


def test_asking_how_much_to_invest_also_explains_the_e_wallet(db):
    tap_campaign(db)
    say(db, "Kitna invest karna hoga?")
    assert bot_messages.MESSAGES["en"]["invest_explained"] in StubMeta.sent[-1][2]


@pytest.fixture
def emailed(monkeypatch):
    from src.services import notifier
    sent = []
    monkeypatch.setattr(notifier, "notify_attention",
                        lambda to, summary, text, url: sent.append({"to": to, "summary": summary, "text": text}) or True)
    return sent


def test_a_question_left_for_a_person_is_emailed_with_the_summary(db, emailed):
    tap_campaign(db)
    say(db, SERVED_PIN)
    say(db, "Mere ghar ka pata badalna hai, kya karna hoga?")
    assert len(emailed) == 1
    text = emailed[0]["text"]
    assert f"Phone:     {PHONE}" in text and "PIN code:" in text and "District:" in text and "Tehsil:" in text
    # The team reads it in Hinglish (the user, 2026-10-23).
    assert "SHORT MEIN" in text and "AB TAK KI BAATCHEET" in text
    assert "Poocha: “Mere ghar ka pata badalna hai, kya karna hoga?”. Aapke reply ka wait hai." in text
    assert "SAWAAL JO AAPKE REPLY KA WAIT KAR RAHE HAIN" in text and "AAGE KYA KAREIN" in text
    # A second question straight after is one email, not two.
    say(db, "Aur kya documents lagenge?")
    assert len(emailed) == 1 or emailed[-1]["summary"]["attention"]["reason"] != emailed[0]["summary"]["attention"]["reason"]


def test_a_question_the_faq_answers_sends_no_email(db, emailed):
    tap_campaign(db)
    say(db, "Apply karne ki fees kitni hai?")
    assert emailed == []


def test_the_summary_shows_questions_answers_and_what_to_send_next(db, client):
    tap_campaign(db)
    say(db, SERVED_PIN)
    qualify(db)                                   # now at the investment question
    say(db, "Kitna invest karna hoga?")           # answered from the FAQ
    say(db, "Mera naam Ravi hai")                 # something else
    r = client.get(f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}/summary")
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["person"]["phone"] == PHONE
    assert any(line.startswith("PIN 110001 diya") for line in s["story"])
    q = s["questions"][-1]
    assert q["text"] == "Kitna invest karna hoga?" and q["answered_by_bot"]
    assert q["answers"][0]["answer"].startswith("₹3–5 lakh, depending")
    assert [o["text"] for o in s["other_messages"]] == ["Mera naam Ravi hai"]
    assert "Investment" in s["next"]["action"] and s["next"]["reply"] == bot_messages.MESSAGES["en"]["ask_invest"]


def test_attention_alerts_list_waiting_conversations_until_resolved(db, client):
    tap_campaign(db)
    say(db, "Mere ghar ka pata badalna hai, kya karna hoga?")
    alerts = client.get("/api/v1/inbox/attention-alerts").json()
    assert [a["phone"] for a in alerts] == [PHONE]
    assert alerts[0]["reason"].startswith("Mere ghar ka pata")
    r = client.post(f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}/attention", json={"needed": False})
    assert r.status_code == 200, r.text
    assert client.get("/api/v1/inbox/attention-alerts").json() == []


def test_a_ticket_is_raised_once_and_solved_with_question_resolved(db, client, emailed):
    tap_campaign(db)
    say(db, "Mere ghar ka pata badalna hai, kya karna hoga?")
    say(db, "Kya aap Sunday ko bhi baat karte ho?")         # a second question: the same ticket
    open_ = client.get("/api/v1/inbox/tickets?status=open").json()
    assert len(open_) == 1
    t = open_[0]
    first = t["ticket_id"]
    assert re.fullmatch(r"TKT-\d{5}", first) and t["status"] == "Not resolved" and t["phone"] == PHONE
    assert t["question"].startswith("Mere ghar ka pata") and t["latest_question"] == "Kya aap Sunday ko bhi baat karte ho?"
    assert t["questions_count"] == 2 and t["raised_via"] == "bot"
    # The alert, the chat and the email all carry the ticket id.
    assert client.get("/api/v1/inbox/attention-alerts").json()[0]["ticket_id"] == first
    assert client.get(f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}").json()["ticket_id"] == first
    assert f"Ticket:    {first}" in emailed[0]["text"]

    r = client.post(f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}/attention", json={"needed": False}).json()
    assert r["ticket"]["status"] == "Resolved" and r["ticket"]["resolved_by"]
    assert client.get("/api/v1/inbox/tickets?status=open").json() == []
    assert [x["ticket_id"] for x in client.get("/api/v1/inbox/tickets/recently-resolved").json()] == [first]
    # A new question after that raises a new ticket.
    say(db, "Ek aur sawal hai, aapka office kahan hai?")
    ids = [x["ticket_id"] for x in client.get("/api/v1/inbox/tickets").json()]
    assert len(ids) == 2 and ids[1] == first and ids[0] > first


def test_team_emails_go_to_the_admin_and_kavya_once_each(monkeypatch):
    from src.services import notifier
    monkeypatch.setattr(notifier, "NOTIFY_ALSO", "kavya.shukla@eko.co.in, Admin@Eko.in")
    assert notifier.team("admin@eko.in") == "admin@eko.in, kavya.shukla@eko.co.in"


def test_a_chat_that_did_not_come_from_a_campaign_is_summarised_for_what_it_is(db, client):
    from src.services import chat_summary
    for i in range(2):
        inbound(db, "image", image={"id": f"m{i}", "mime_type": "image/jpeg"})
    say(db, "isko install karna hai sir")
    c = conv(db)
    assert c.bot_step is None
    s = chat_summary.summarise(db, c)
    assert s["direct"] and s["headline"] == "Seedha humein likha"
    assert "seedha humein likha" in s["in_short"] and "2 photo bheja" in s["in_short"]
    assert "device install ya setup karna" in s["in_short"] and "Abhi tak kisi ne reply nahi kiya" in s["in_short"]
    assert "2 photo bheje" in [t["text"] for t in s["timeline"]]
    assert "Interested" not in s["next"]["action"] and "support team" in s["next"]["action"]
    assert s["next"]["reply"].startswith("Namaste") and s["next"]["reply_language"] == "Hinglish"
    # The team's own reply shows in the conversation and in short.
    inbox.send(db, PHONE, "Ji, hum aapko call karte hain", sent_by="kavya.shukla@eko.co.in")
    db.commit()
    s = chat_summary.summarise(db, conv(db))
    assert any(t["kind"] == "team" and t["text"].startswith("Kavya Shukla ne reply kiya") for t in s["timeline"])
    assert "Team ne" in s["in_short"] and "reply kiya" in s["in_short"]



# --- Handover between the bot and a person, and dispositions ------------------

def test_a_reply_by_hand_takes_the_chat_over_and_handing_back_asks_again(db, client):
    from src.services import chat_summary, handover
    tap_campaign(db)
    say(db, SERVED_PIN)                                   # now asked for their education
    assert conv(db).bot_step == onboarding_bot.AWAIT_EDUCATION
    r = client.post(f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}/messages", json={"message": "Main Kavya, bataiye"})
    assert r.status_code == 200, r.text
    c = conv(db)
    assert c.bot_paused and c.handled_by == "admin@eko.co.in"
    detail = client.get(f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}").json()
    assert detail["handled_by"] == "admin@eko.co.in"
    # While a person handles it the bot stays quiet; a question waits for them.
    before = len(StubMeta.sent)
    say(db, "Kya training milegi?")
    assert len(StubMeta.sent) == before and conv(db).needs_attention

    r = client.post(f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}/handover",
                    json={"to": "bot", "disposition": "interested", "note": "Answered about training"})
    assert r.status_code == 200, r.text
    c = conv(db)
    assert not c.bot_paused and c.handled_by is None and not c.needs_attention
    # The bot asks again the question it was waiting on, after a short thank-you.
    body = StubMeta.sent[-1][2]
    assert body.startswith(bot_messages.MESSAGES["en"]["resume"]) and bot_messages.MESSAGES["en"]["ask_education"] in body
    # An old key is still understood, and comes back as today's.
    assert r.json()["disposition"]["key"] == "int_in_bot_flow" and r.json()["disposition"]["source"] == "team"
    kinds = [a["kind"] for a in client.get(f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}/activity").json()]
    assert kinds == ["to_person", "disposition", "to_bot"]
    lines = [t["text"] for t in chat_summary.summarise(db, conv(db))["timeline"]]
    assert "Admin ne bot se chat le li" in lines
    assert "Admin ne chat wapas bot ko di (Interested: in the bot's questions)" in lines

    # The bot moving the chat on later makes its own outcome the current one.
    qualify(db)
    assert handover.current(conv(db))["source"] == "bot"


def test_every_chat_has_a_disposition_and_the_dashboard_counts_them(db, client):
    tap_campaign(db)
    say(db, SERVED_PIN)
    # Read from the bot's step: in its questions, not yet ready to proceed.
    assert client.get(f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}").json()["disposition"]["key"] == "int_in_bot_flow"
    r = client.post(f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}/disposition",
                    json={"disposition": "call_back", "note": "Call after 6 PM"})
    assert r.status_code == 200 and r.json()["label"] == "Asked to call later"
    assert client.post(f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}/disposition",
                       json={"disposition": "nonsense"}).status_code == 400
    d = client.get("/api/v1/inbox/dispositions/dashboard").json()
    assert d["total"] == 1 and d["by_team"] == 1 and d["recent_count"] == 1
    assert next(g for g in d["groups"] if g["key"] == "busy_later")["count"] == 1
    busy = next(c for c in d["categories"] if c["key"] == "busy")
    assert busy["label"] == "Busy / Callback" and busy["count"] == 1
    assert d["recent"][0]["note"] == "Call after 6 PM"


def test_question_resolved_records_the_disposition(db, client):
    tap_campaign(db)
    say(db, "Mere ghar ka pata badalna hai, kya karna hoga?")
    r = client.post(f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}/attention",
                    json={"needed": False, "disposition": "query_answered"})
    assert r.status_code == 200, r.text
    assert conv(db).disposition == "int_more_info"


def test_the_bot_solves_what_it_knows_and_escalates_the_rest(db, client, emailed):
    tap_campaign(db)
    say(db, "CIBIL score kitna chahiye?")                  # from kiosk.eko.in: the bot answers
    assert "700" in StubMeta.sent[-1][2] and not conv(db).needs_attention
    solved = client.get("/api/v1/inbox/tickets?status=resolved").json()
    assert len(solved) == 1 and solved[0]["resolved_by_bot"] and "700" in solved[0]["bot_answer"]
    assert solved[0]["question"] == "CIBIL score kitna chahiye?"
    # Nobody was waiting on it, so it is not announced as a solved ticket.
    assert client.get("/api/v1/inbox/tickets/recently-resolved").json() == []
    assert emailed == []

    say(db, "Mere ghar ka pata badalna hai, kya karna hoga?")   # not in what it knows: to a person
    assert conv(db).needs_attention and len(emailed) == 1
    open_ = client.get("/api/v1/inbox/tickets?status=open").json()
    assert len(open_) == 1 and not open_[0]["resolved_by_bot"]


def test_the_team_emails_go_to_mansi_and_kavya():
    from src.services import auth_service, notifier
    assert "kavya.shukla@eko.co.in" in notifier.team(auth_service.BOOTSTRAP_ADMIN)


# --- The bot understands a question however it is put ---------------------------

SAME_QUESTION = {
    "job": ["Ye bank ki naukari hai?", "Kya yeh bank ki naukri hai?", "kya ye nokri hai", "Kya main bank ka employee banunga?",
            "क्या ये बैंक की नौकरी है?", "ਕੀ ਇਹ ਬੈਂਕ ਦੀ ਨੌਕਰੀ ਹੈ?", "શું આ બેંકની નોકરી છે?", "is this a bank job?"],
    "investment": ["Eko ke saath SBI CSP kholne ke liye kuch paisa lagega?", "Kuch invest krna hoga?", "kitna paisa lagana padega", "कितना निवेश करना होगा", "ਕਿੰਨਾ ਨਿਵੇਸ਼ ਕਰਨਾ ਪਵੇਗਾ", "કેટલું રોકાણ કરવું પડશે"],
    "earnings": ["Kamayi kitni hogi mahine ki?", "कितनी कमाई होगी", "ਕਿੰਨੀ ਕਮਾਈ ਹੋਵੇਗੀ", "કેટલી કમાણી થશે", "how much can I earn"],
    "documents": ["kaun se kagaz lagenge", "कौन से दस्तावेज चाहिए", "ਕਿਹੜੇ ਦਸਤਾਵੇਜ਼ ਚਾਹੀਦੇ", "aadhar card chahiye?"],
    "real": ["kya ye sach me hai", "Eko kya company hai?", "is this genuine or scam"],
    "salary": ["fix salary milegi?", "kya har mahine pakka paisa milega"],
    # The rest of kiosk.eko.in.
    "what_csp": ["CSP kya hota hai?", "सीएसपी क्या है", "Ye CSP ka kya matlab hai?", "csp ka meaning batao"],
    "setup_cost": ["setup ka kharcha kitna", "machine ke paise lagenge?"],
    "who_fits": ["banking experience chahiye?", "housewife kar sakti hai?"],
    "schemes": ["atal pension yojana kar sakte", "pmjjby kya hai"],
    "security": ["data surakshit hai?", "क्या ये सुरक्षित है"],
    "audit": ["koi check karne aayega?"],
    "ngo": ["hamari NGO kaise jude"],
    "apply_online": ["aap call kab karenge", "form kahan bharna hai"],
    "process": ["Eko ke saath me SBI ki CSP kese ban sakti hoon?", "Eko ke saath me Kiosk Operator kese ban sakti hoon?",
                "How do I become a Kiosk Operator?", "SBI CSP kaise milega", "सीएसपी कैसे बनें"],
}
NOT_IN_THE_FAQ = ["Mere ghar ka pata badalna hai, kya karna hoga?", "mera account kaise ban jayega", "Kya aap Sunday ko bhi baat karte ho?",
                  "aapka office kahan hai?", "ATM card kab tak milega sir?", "Thank you", "Namaste sar aaj ki chutti hai kya",
                  "Shivani madam contact number account list problem", "Thank you for contacting Aditya mobile store!"]


@pytest.mark.parametrize("faq_id,question", [(f, q) for f, qs in SAME_QUESTION.items() for q in qs])
def test_the_same_question_asked_another_way_finds_the_same_answer(faq_id, question):
    from src.services import eko_knowledge
    assert eko_knowledge.match(question)[:1] == [faq_id]


@pytest.mark.parametrize("question", NOT_IN_THE_FAQ)
def test_a_question_the_faq_does_not_cover_is_not_forced_onto_it(question):
    from src.services import eko_knowledge
    assert eko_knowledge.match(question) == []


def test_naukari_spelt_differently_is_answered_by_the_bot(db):
    tap_campaign(db)
    say(db, "Ye bank ki naukari hai?")
    assert StubMeta.sent[-1][2].startswith("No. This is your own business.")
    assert not conv(db).needs_attention


def test_the_site_figures_come_with_the_sites_own_warning():
    from src.services import eko_knowledge
    said = eko_knowledge.reply(eko_knowledge.match("kitni kamai hogi"), "hi", "kitni kamai hogi")
    assert "₹15,000" in said and "₹33,768" in said and "kaafi kam" in said
    assert said.startswith("Har seva aur har enrolment par commission")   # the confirmed answer first
    # The template agents still get the Creator Pack's words, without figures.
    assert "₹33,768" not in eko_knowledge.agent_section()


def test_the_team_can_teach_the_bot_a_new_way_of_asking(db, client):
    from src.services import eko_knowledge
    tap_campaign(db)
    say(db, "Isse bacchon ki school fees nikal aayegi na?")      # not recognised: to a person
    assert conv(db).needs_attention
    r = client.post("/api/v1/inbox/faq/teach", json={"faq_id": "earnings", "phone": PHONE,
                                                       "question": "Isse bacchon ki school fees nikal aayegi na?"})
    assert r.status_code == 200, r.text
    assert r.json()["answer"].startswith("Commission on every service")
    try:
        # Asked again, a little differently, the bot now answers it itself.
        assert eko_knowledge.match("isse bacchon ki school fees nikal aayegi kya") == ["earnings"]
        assert eko_knowledge.match("ghar ka pata badalna hai") == []
        listed = {a["id"]: a for a in client.get("/api/v1/inbox/faq").json()}
        assert listed["earnings"]["taught"] == ["Isse bacchon ki school fees nikal aayegi na?"]
        assert client.post("/api/v1/inbox/faq/teach", json={"faq_id": "nope", "question": "x"}).status_code == 400
    finally:
        client.request("DELETE", "/api/v1/inbox/faq/teach",
                       json={"faq_id": "earnings", "question": "Isse bacchon ki school fees nikal aayegi na?"})
    assert eko_knowledge.LEARNED == {}


def test_a_file_that_can_carry_malware_is_blocked_not_opened(db, client, emailed):
    StubMeta.media["zip1"] = (b"PK\x03\x04 not really", "application/zip")
    tap_campaign(db)
    before = len(StubMeta.sent)
    msg = inbound(db, "document", document={"id": "zip1", "mime_type": "application/x-zip-compressed", "filename": "SOA.zip"})
    m = db.get(WhatsAppMessage, msg.message_id)
    assert "malware" in m.payload["blocked"] and "stored" not in m.payload
    assert inbox.fetch_media(m).startswith("Blocked") and "stored" not in m.payload    # never downloaded
    r = client.get(f"/api/v1/inbox/media/{msg.message_id}")
    assert r.status_code == 403
    thread = client.get(f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}").json()["messages"]
    shown = next(t for t in thread if t["id"] == msg.message_id)
    assert shown["payload"]["blocked"] and "media_id" not in shown["payload"]
    c = conv(db)
    assert c.needs_attention and c.attention_reason.startswith("Unsafe file blocked: SOA.zip")
    assert len(StubMeta.sent) == before        # the bot says nothing to it
    assert len(emailed) == 1
    # A PDF is still an ordinary document.
    assert inbox.unsafe_reason({"filename": "aadhaar.pdf", "mime_type": "application/pdf"}) is None
    assert inbox.unsafe_reason({"filename": "old.zip", "stored": "data/inbox_media/1/x.zip"})   # stored before the rule


def test_the_teams_solved_test_tickets_are_left_out_not_deleted(db, client, monkeypatch):
    from src.services import campaign_insights
    tap_campaign(db)
    say(db, "Mere ghar ka pata badalna hai, kya karna hoga?")
    client.post(f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}/attention", json={"needed": False})
    assert len(client.get("/api/v1/inbox/tickets?status=resolved").json()) == 1
    # The same number turns out to be the team's own test phone.
    monkeypatch.setattr(campaign_insights, "team_phones", lambda db: {PHONE})
    assert client.get("/api/v1/inbox/tickets?status=resolved").json() == []
    assert client.get("/api/v1/inbox/tickets/recently-resolved").json() == []
    assert len(client.get("/api/v1/inbox/tickets?status=resolved&include_tests=true").json()) == 1   # still kept
    # An open ticket from a test number still shows, for testing the flow.
    say(db, "Kya aap Sunday ko bhi baat karte ho?")
    assert len(client.get("/api/v1/inbox/tickets?status=open").json()) == 1


# Questions that name the subject (CSP, SBI, Eko, kiosk) but ask different
# things, typed the many ways people type; and complaints from people already
# running a CSP, which are the team's to answer. faq null: goes to a person.
import json as _json
import pathlib as _pathlib

CONFUSING = _json.loads((_pathlib.Path(__file__).parent / "data" / "confusing_questions.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CONFUSING, ids=[c["question"][:40] for c in CONFUSING])
def test_a_confusing_question_finds_the_right_answer_or_a_person(case):
    from src.services import eko_knowledge
    got = eko_knowledge.match(case["question"])
    if case["faq"] is None:
        assert got == []
    else:
        assert got and got[0] == case["faq"]


def test_hindi_written_in_latin_letters_is_answered_in_latin_letters(db):
    tap_campaign(db, lang="hi")
    say(db, SERVED_PIN)
    say(db, "Kuch invest krna hoga?")
    body = StubMeta.sent[-1][2]
    assert body.startswith("INR 3–5 lakh") and "₹3–5 lakh (aapki location ke hisaab se) ka istemal kaise hota hai" in body
    assert not re.search(r"[\u0900-\u097F]{3,}", body)        # no Devanagari sentences left in it
    # Written in Devanagari, the bot answers in Devanagari again.
    say(db, "कितना निवेश करना होगा?")
    assert "₹3–5 लाख (आपकी लोकेशन के अनुसार) का इस्तेमाल" in StubMeta.sent[-1][2]


def test_an_inbox_limited_to_other_chats_never_shows_an_autogmap_one(db, client):
    from src.routers import inbox as inbox_router
    tap_campaign(db)                                                     # PHONE: an AutoGMap chat
    say(db, "Mere ghar ka pata badalna hai, kya karna hoga?")            # with a ticket
    inbox.record_inbound(db, {"from": OTHER.lstrip("+"), "id": "wamid.other1", "type": "text",
                              "text": {"body": "ATM card kab milega?"}}, "Other team's contact")
    db.commit()

    async def not_autogmap():
        inbox_router._SCOPE.set("not_autogmap")
    app.dependency_overrides[inbox_router._bind_scope] = not_autogmap
    try:
        phones = [c["phone"] for c in client.get("/api/v1/inbox/conversations").json()]
        assert phones == [OTHER]
        assert client.get(f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}").status_code == 404
        assert client.get(f"/api/v1/inbox/conversations/{OTHER.lstrip('+')}").status_code == 200
        assert client.get("/api/v1/inbox/attention-alerts").json() == []
        assert client.get("/api/v1/inbox/tickets").json() == []
        assert client.post(f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}/messages",
                           json={"message": "hi"}).status_code == 404
    finally:
        app.dependency_overrides.pop(inbox_router._bind_scope, None)
    # Everyone else still sees both.
    assert {c["phone"] for c in client.get("/api/v1/inbox/conversations").json()} == {PHONE, OTHER}



# --- Personal guidance: ask, get answers, start when ready (2026-10-21) -------------

def _guidance(db, lang="hi"):
    tap_campaign(db, text=campaign_buttons.WEBINAR["en"], lang=lang)


def test_personal_guidance_invites_questions_instead_of_booking(db):
    _guidance(db)
    kind, _to, body, buttons = StubMeta.sent[-1]
    assert body == bot_messages.MESSAGES["hi"]["guidance_open"]
    assert [b["id"] for b in buttons] == [onboarding_bot.START_INTERESTED]
    assert conv(db).bot_step == onboarding_bot.GUIDANCE_QA
    assert "available" not in body.lower() and "उपलब्ध" not in body


def test_a_guidance_question_the_faq_covers_is_answered_kindly(db, emailed):
    _guidance(db)
    say(db, "Kitna invest karna hoga?")
    body = StubMeta.sent[-1][2]
    assert body.startswith("Achha sawaal! 😊") and "5 lakh" in body
    assert body.rstrip().endswith(bot_messages.HINGLISH["guidance_more"])
    c = conv(db)
    assert c.bot_step == onboarding_bot.GUIDANCE_QA and not c.needs_attention and emailed == []


def test_a_guidance_question_it_cannot_answer_goes_to_a_person(db, emailed):
    from src.services import tickets
    _guidance(db, lang="en")
    say(db, "Kya aap Sunday ko bhi baat karte ho?")
    body = StubMeta.sent[-1][2]
    assert body.startswith(bot_messages.HINGLISH["question_ack"]) or body.startswith(bot_messages.MESSAGES["en"]["question_ack"])
    c = conv(db)
    assert c.needs_attention and c.bot_step == onboarding_bot.GUIDANCE_QA
    assert tickets.open_ticket(db, PHONE) is not None and len(emailed) == 1


@pytest.mark.parametrize("said", ["Haan main interested hoon", "mujhe judna hai", "I want to start", "मुझे शुरू करना है"])
def test_saying_they_are_interested_starts_the_application(db, said):
    _guidance(db)
    say(db, said)
    c = conv(db)
    assert c.bot_step == onboarding_bot.AWAIT_PIN
    assert StubMeta.sent[-1][2] in (bot_messages.MESSAGES["hi"]["ask_pin"], bot_messages.HINGLISH["ask_pin"])


def test_tapping_interested_during_guidance_starts_the_application(db):
    _guidance(db)
    tap(db, onboarding_bot.START_INTERESTED)
    assert conv(db).bot_step == onboarding_bot.AWAIT_PIN


def test_not_interested_does_not_start_it(db):
    _guidance(db)
    say(db, "abhi interested nahi hoon")
    assert conv(db).bot_step == onboarding_bot.GUIDANCE_QA


def test_a_pin_during_guidance_begins_with_that_pin(db):
    _guidance(db)
    say(db, SERVED_PIN)
    assert conv(db).bot_step == onboarding_bot.AWAIT_EDUCATION


def test_the_guidance_button_in_a_regional_language_is_recognised(db):
    _punjabi_campaign(db)
    tap_campaign(db, text=campaign_buttons.WEBINAR["pa"], lang="pa")
    assert StubMeta.sent[-1][2] == bot_messages.MESSAGES["pa"]["guidance_open"]


def test_the_language_is_remembered_for_the_application(db):
    _guidance(db)
    count = len(StubMeta.sent)
    tap_campaign(db, lang=None)              # Interested on the campaign, after guidance
    assert len(StubMeta.sent) == count + 1
    assert StubMeta.sent[-1][2] == bot_messages.MESSAGES["hi"]["ask_pin"]


def test_someone_left_at_the_old_availability_question_is_answered_the_new_way(db):
    _guidance(db, lang="en")
    c = conv(db)
    c.bot_step = onboarding_bot.AWAIT_AVAILABILITY
    db.commit()
    say(db, "Kitna invest karna hoga?")
    assert conv(db).bot_step == onboarding_bot.GUIDANCE_QA
    assert "5 lakh" in StubMeta.sent[-1][2]


def test_every_language_has_the_guidance_messages():
    for lang, msgs in bot_messages.MESSAGES.items():
        assert msgs["guidance_open"] and msgs["guidance_more"] and msgs["guidance_intro"], lang



# --- The dispositions sheet, and nudges standing in for calls (2026-10-21) ----

from src.services import dispositions as dz, followups, nudge_messages, reply_language  # noqa: E402


def _followups(db):
    from src.models.inbox import FollowUp
    return db.query(FollowUp).filter(FollowUp.phone == PHONE).order_by(FollowUp.created_at, FollowUp.due_at).all()


def _a_day_ago(db):
    """Move the chat's messages back two days, as if the nudge had been sent a day ago after them."""
    from datetime import timedelta
    for m in db.query(WhatsAppMessage).filter(WhatsAppMessage.phone == PHONE).all():
        m.created_at = inbox.aware(m.created_at) - timedelta(days=2)
    db.commit()


def _record(client, key, **extra):
    r = client.post(f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}/disposition", json={"disposition": key, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def test_the_sheet_has_its_eleven_categories_and_every_sub_category():
    sheet = [c for c in dz.CATEGORIES if c.key != "other"]
    assert [c.label for c in sheet] == [
        "Interested", "Not Interested", "Rejected", "Busy / Callback", "RNR", "Unreachable", "Invalid Lead",
        "Duplicate / Existing", "Not Decision Maker", "Hold / Future Prospect", "Language Barrier"]
    labels = {s.label for c in sheet for s in c.subs}
    for wanted in ("Physical visit required", "More information required", "Callback requested",
                   "Documents pending", "Investment issue", "Applied by mistake", "No requirement",
                   "Not interested currently", "Low credit score", "Eligibility criteria not met",
                   "Busy", "Asked to call later", "Call at specific time", "No answer", "Ringing but not picked",
                   "Switched off", "Out of coverage", "Number not reachable",
                   "Person denied applying", "Incorrect customer details", "Duplicate lead", "Already in process",
                   "Existing customer / existing CSP", "Person contacted is not applicant",
                   "Decision maker not available", "Interested later", "Financial constraint currently",
                   "Wants to proceed after certain date", "Cannot communicate due to language mismatch"):
        assert wanted in labels, wanted
    # Off the list in the user's sheet of 23 Oct 2026; the hand-over is the bot's alone.
    assert not {"Wrong number", "Invalid number", "Replacement not available in current AO"} & labels
    picks = {o["key"] for o in dz.options()}
    assert "int_visit" not in picks and "int_not_sbi" in picks
    assert dz.normalise("inv_wrong_number") == "inv_incorrect" and dz.normalise("hold_no_replacement") == "hold_financial"
    # Every older key still means something.
    assert all(dz.normalise(k) in dz.SUBS for k in dz.LEGACY)


def test_every_nudge_is_written_in_every_language_without_blanks():
    for purpose in nudge_messages.PURPOSES:
        for v in nudge_messages.VARIANTS:
            text = nudge_messages.TEXT[purpose].get(v)
            assert text, (purpose, v)
            assert "{{" not in text and "Eko" in text
    # Every message step of every disposition has its nudge (a task is for a person).
    assert {st.purpose for s in dz.SUBS.values() for st in s.steps
            if st.wants not in (dz.API, dz.TASK, dz.ESCALATE)} <= set(nudge_messages.PURPOSES)


@pytest.mark.parametrize("text,chat,expected", [
    ("મને વધુ માહિતી જોઈએ છે", "en", ("gu", False)),
    ("ਮੈਨੂੰ ਹੋਰ ਜਾਣਕਾਰੀ ਚਾਹੀਦੀ ਹੈ", "en", ("pa", False)),
    ("मुझे और जानकारी चाहिए", "en", ("hi", False)),
    ("मला अधिक माहिती हवी आहे", "mr", ("mr", False)),
    ("Mujhe aur jankari chahiye bhai", "en", ("hi", True)),
    ("Please call me in the evening", "hi", ("en", False)),
    ("ok", "hi", None),
])
def test_the_language_of_a_reply_is_read_from_its_letters(text, chat, expected):
    assert reply_language.of_text(text, chat) == expected


def test_a_nudge_goes_in_the_language_of_their_last_message(db, client):
    tap_campaign(db, lang="en")
    # "Call me later, I am busy now": the bot records it itself, and answers in Gujarati.
    say(db, "મને પછી ફોન કરજો, અત્યારે હું વ્યસ્ત છું")
    assert conv(db).disposition == "busy_later" and conv(db).disposition_by == "bot"
    assert StubMeta.sent[-1][2] == nudge_messages.text("callback_confirm", "gu")
    callback = [f for f in _followups(db) if f.purpose == "callback_due"][0]
    assert callback.status == "scheduled" and callback.wants == dz.CALL


def test_hindi_in_latin_letters_gets_the_hinglish_nudge(db, client):
    tap_campaign(db, lang="hi")
    say(db, "Abhi paisa nahi hai mere paas")
    _record(client, "ni_investment")
    assert StubMeta.sent[-1][2] == nudge_messages.text("lower_investment", nudge_messages.HINGLISH)


def test_a_callback_at_a_set_time_is_due_then(db, client):
    from datetime import timedelta
    tap_campaign(db)
    when = inbox.now() + timedelta(hours=3)
    _record(client, "busy_at_time", at=when.isoformat())
    due = [f for f in _followups(db) if f.purpose == "callback_due"][0]
    assert abs((inbox.aware(due.due_at) - when).total_seconds()) < 2


def test_calls_the_sheet_asks_for_go_as_nudges_until_calling_is_on(db, client):
    tap_campaign(db)
    say(db, "I have a few questions about the setup")
    _record(client, "int_more_info")
    f = _followups(db)[0]
    assert f.wants == "whatsapp_call" and f.channel == "whatsapp_nudge" and f.status == "sent"
    assert "WhatsApp call: WhatsApp calling is not switched on yet" in f.note


def test_no_answer_in_a_day_is_rnr_and_tried_again_the_next_day(db, client):
    from datetime import timedelta
    tap_campaign(db)
    say(db, "I have a few questions about the setup")
    _record(client, "int_more_info")
    _a_day_ago(db)
    f = _followups(db)[0]
    f.sent_at = inbox.now() - timedelta(hours=25)
    db.commit()
    followups.tick(db)
    db.expire_all()
    assert conv(db).disposition == "rnr_no_answer" and conv(db).disposition_by == "bot"
    retry = [x for x in _followups(db) if x.purpose == "missed_you"][0]
    assert retry.attempt == 2 and retry.status == "scheduled"
    assert inbox.aware(retry.due_at) > inbox.now()


def test_a_reply_answers_it_and_cancels_the_next_day_retry(db, client):
    tap_campaign(db)
    _record(client, "rnr_no_answer")
    retry = _followups(db)[0]
    assert retry.status == "scheduled"
    # Meta stamps messages to the second; the reply comes a while after.
    from datetime import timedelta
    retry.created_at = inbox.now() - timedelta(minutes=5)
    db.commit()
    say(db, "Sorry, I missed your message")
    followups.tick(db)
    db.expire_all()
    assert _followups(db)[0].status == "cancelled"


def test_an_undelivered_nudge_is_unreachable_and_tried_again(db, client):
    tap_campaign(db)
    StubMeta.ok = False
    _record(client, "int_more_info")
    db.expire_all()
    assert conv(db).disposition == "unr_not_reachable"
    assert any(x.purpose == "missed_you" and x.attempt == 2 for x in _followups(db))


def test_retries_stop_after_three_attempts(db, client):
    from datetime import timedelta
    tap_campaign(db)
    say(db, "I have a few questions about the setup")
    _record(client, "int_more_info")
    _a_day_ago(db)
    f = _followups(db)[0]
    f.attempt, f.sent_at = followups.MAX_ATTEMPTS, inbox.now() - timedelta(hours=25)
    db.commit()
    followups.tick(db)
    db.expire_all()
    assert conv(db).disposition == "int_more_info"            # not chased again
    assert "Stopped after 3 attempts" in _followups(db)[0].note


def test_outside_the_window_it_waits_for_an_approved_template_then_sends_it(db, client):
    from datetime import timedelta
    from src.models.whatsapp import WhatsAppTemplate
    tap_campaign(db)
    c = conv(db)
    c.last_inbound_at = inbox.now() - timedelta(days=2)
    db.commit()
    _record(client, "hold_later", at=(inbox.now() - timedelta(days=1)).isoformat())   # due already
    followups.tick(db)
    f = [x for x in _followups(db) if x.purpose == "checking_in"][0]
    assert f.status == "waiting" and "not approved" in f.note
    db.add(WhatsAppTemplate(template_id=uuid.uuid4().hex, name="nudge_checking_in_en", status="APPROVED",
                            meta_template_name="eko_nudge_checking_in", language_code="en", body="x", origin="nudge"))
    db.commit()
    followups.tick(db)
    db.expire_all()
    assert [x for x in _followups(db) if x.purpose == "checking_in"][0].status == "sent"
    assert StubMeta.sent[-1][:3] == ("template", PHONE, "eko_nudge_checking_in")


def test_a_closing_disposition_cancels_everything_pending(db, client):
    tap_campaign(db)
    _record(client, "lang_barrier")
    _record(client, "inv_wrong_number")
    assert not any(f.status in ("scheduled", "waiting") for f in _followups(db))


def test_nudge_templates_are_listed_for_review_and_kept_out_of_campaigns(db, client):
    from src.models.whatsapp import WhatsAppTemplate
    listed = client.get("/api/v1/inbox/dispositions/nudge-templates").json()
    assert len(listed) == len(nudge_messages.PURPOSES)
    assert all(len(p["variants"]) == 12 and all(v["status"] == "NOT_SUBMITTED" for v in p["variants"]) for p in listed)
    assert {v["meta_name"] for v in listed[0]["variants"]} == {"eko_nudge_more_info", "eko_nudge_more_info_hinglish"}
    db.add(WhatsAppTemplate(template_id=uuid.uuid4().hex, name="nudge_missed_you_en", status="APPROVED",
                            meta_template_name="eko_nudge_missed_you", language_code="en", body="x", origin="nudge"))
    db.commit()
    assert all(t["name"] != "nudge_missed_you_en" for t in client.get("/api/v1/whatsapp/templates").json())



def test_the_interested_journey_sets_nothing_in_motion(db):
    # Tapping Interested and answering the bot records no disposition and plans no follow-up:
    # only a person recording one does.
    tap_campaign(db)
    say(db, SERVED_PIN)
    qualify(db)
    assert conv(db).disposition is None and _followups(db) == []
    from src.services import handover
    assert handover.current(conv(db))["key"] == "int_in_bot_flow"



# --- Where AutoGMap's part ends, and every lead's journey (2026-10-21) --------

def _upload(db, client):
    tap_campaign(db)
    say(db, SERVED_PIN)
    qualify(db)
    tap(db, "invest:yes")
    tap(db, "docs:yes")
    c = conv(db)
    assert client.post(f"/onboard/{c.upload_token}/submit").status_code in (200, 400)
    c.documents_submitted_at = c.documents_submitted_at or inbox.now()
    c.bot_step = onboarding_bot.SUBMITTED
    db.commit()


def test_ready_to_proceed_and_cat_1_are_eko_acquisitions_not_ours():
    labels = {s.label for s in dz.SUBS.values()}
    assert "Ready to proceed" not in labels and not any(s.stage == "CAT 1" for s in dz.SUBS.values())
    assert "BM not agree" not in labels
    for gone in ("next_steps", "visit_planned", "other_bank"):
        assert gone not in nudge_messages.PURPOSES


def test_physical_visit_required_hands_over_and_sets_nothing_in_motion(db, client):
    tap_campaign(db)
    _record(client, "int_docs_pending")
    assert any(f.status == "scheduled" for f in _followups(db))
    _record(client, "int_visit")
    # Nothing goes to the person any more; the lead is queued for Eko Acquisition's API.
    assert not any(f.status in ("scheduled", "waiting") and f.wants != dz.API for f in _followups(db))
    assert not any(f.wants == dz.TASK for f in _followups(db))
    to_them = [f for f in _followups(db) if f.wants == dz.API]
    assert len(to_them) == 1 and to_them[0].status == "waiting" and "not set up yet" in to_them[0].note
    d = client.get("/api/v1/inbox/dispositions/dashboard").json()
    assert d["handed_over"] == 1 and "cat1" not in d


def test_uploading_documents_ends_our_part_and_stops_reminders(db, client):
    tap_campaign(db)
    _record(client, "int_docs_pending")                    # a reminder due in 2 days
    c = conv(db)
    c.documents_submitted_at = inbox.now()
    db.commit()
    followups.tick(db)
    db.expire_all()
    assert all(f.status != "scheduled" for f in _followups(db))
    from src.services import handover
    assert handover.current(conv(db))["key"] == "int_visit"


def test_a_leads_journey_has_each_step_with_its_date_and_our_action(db, client):
    from src.services import lead_journey
    _upload(db, client)
    j = client.get(f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}/journey").json()
    stages = [s for s in j["steps"] if s["kind"] == "stage"]
    keys = [s["key"] for s in stages]
    for k in ("interested", "pin", "education", "investment", "docs_ready", "uploaded", "handed_over"):
        assert k in keys, (k, keys)
    assert keys.index("interested") < keys.index("pin") < keys.index("investment") < keys.index("handed_over")
    pin = next(s for s in stages if s["key"] == "pin")
    assert pin["at"] and pin["action"] == "Asked about their education" and pin["action_at"]
    last = stages[-1]
    assert last["key"] == "handed_over" and last["by"] == "Eko Acquisition"
    assert "Assign to DC, schedule visit, DC will give report to Eko" in last["action"]
    assert j["outcome"] == "handed_over" and j["furthest"] == lead_journey.FUNNEL.index("handed_over")


def test_the_journey_shows_negative_turns_and_team_actions(db, client):
    tap_campaign(db)
    say(db, SERVED_PIN)
    qualify(db)
    tap(db, "invest:no")                                    # cannot invest
    _record(client, "ni_investment", note="Asked about EMI")
    j = client.get(f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}/journey").json()
    whats = [s["what"] for s in j["steps"] if s["what"]]
    assert "Cannot invest right now" in whats
    # The bot records "Investment issue" itself; the team's own record follows it.
    rec = [s for s in j["steps"] if s["key"] == "disposition:ni_investment"][-1]
    assert rec["detail"] == "Asked about EMI" and rec["by"] == "admin@eko.co.in"
    assert any(s["key"] == "nudge" and "lower-investment" in s["action"] for s in j["steps"])
    assert j["outcome"] == "closed"


def test_the_journeys_list_has_every_lead_that_did_something(db, client):
    tap_campaign(db)
    say(db, SERVED_PIN)
    rows = client.get("/api/v1/inbox/dispositions/journeys").json()
    assert [r["phone"] for r in rows] == [PHONE]
    assert rows[0]["furthest"] >= 3 and rows[0]["outcome"] == "in_progress"


def test_bot_messages_are_recognised_in_every_language():
    from src.services import lead_journey
    for lang, msgs in bot_messages.MESSAGES.items():
        assert lead_journey.classify(msgs["ask_education"]) == "ask_education", lang
        assert lead_journey.classify(msgs["nudge"] + "\n\n" + msgs["ask_pin"]) == "nudge", lang
    assert lead_journey.classify(bot_messages.HINGLISH["ask_pin"]) == "ask_pin"
    assert lead_journey.classify("Training is given free by Eko.") is None


def test_steps_planned_before_the_handover_rules_are_cancelled(db):
    from src.models.inbox import FollowUp
    tap_campaign(db)
    db.add(FollowUp(followup_id=uuid.uuid4().hex, phone=PHONE, disposition="int_visit", purpose="visit_planned",
                    owner="dc", wants=dz.TASK, due_at=inbox.now(), status="scheduled", created_by="x", task="Visit"))
    db.add(FollowUp(followup_id=uuid.uuid4().hex, phone=PHONE, disposition="int_ready", purpose="next_steps",
                    owner="bot", wants=dz.NUDGE, due_at=inbox.now(), status="waiting", created_by="x"))
    db.commit()
    followups.tick(db)
    db.expire_all()
    assert {f.status for f in _followups(db)} == {"cancelled"}



# --- Who hears about a disposition, and the hand-over to Eko Acquisition ------

@pytest.fixture
def team_mail(monkeypatch):
    """The team emails, sent at once rather than on a thread."""
    sent = []

    class Now:
        def __init__(self, target, args=(), daemon=None):
            self.target, self.args = target, args

        def start(self):
            self.target(*self.args)

    monkeypatch.setattr(followups.threading, "Thread", Now)
    monkeypatch.setattr(followups, "_email_team", lambda subject, body: sent.append((subject, body)))
    return sent


def test_only_dispositions_the_sheet_gives_a_person_email_the_team():
    human = {k for k, s in dz.SUBS.items() if dz.needs_team(s)}
    # The sheet's "Ticket + email" column (the user's sheet, 2026-10-23).
    assert human == {"int_more_info", "rej_credit", "rej_eligibility", "inv_denied",
                     "ndm_not_applicant", "ndm_unavailable", "hold_later", "hold_financial", "hold_after_date"}


def test_a_disposition_for_a_person_raises_a_ticket_and_emails_the_team(db, client, team_mail):
    from src.services import tickets
    tap_campaign(db)
    say(db, SERVED_PIN)
    _record(client, "rej_credit", note="CIBIL 580")
    assert conv(db).needs_attention and tickets.open_ticket(db, PHONE) is not None
    [(subject, body)] = team_mail
    assert "Low credit score" in subject
    assert "Connect for BT/other proposal" in body and "CIBIL 580" in body and "Journey so far:" in body


def test_a_disposition_for_the_bot_emails_nobody(db, client, team_mail):
    tap_campaign(db)
    _record(client, "busy_busy")
    _record(client, "lang_barrier")
    assert team_mail == [] and not conv(db).needs_attention


def test_uploaded_documents_go_to_eko_acquisitions_api(db, client, monkeypatch):
    from src.services import acquisition_handover
    posted = []

    class Resp:
        status_code, text = 201, "created"

    import requests
    monkeypatch.setattr(requests, "post", lambda url, json=None, headers=None, timeout=None: posted.append((url, json, headers)) or Resp())
    tap_campaign(db)
    c = conv(db)
    onboarding_bot.documents_submitted(db, c)
    db.commit()
    f = [x for x in _followups(db) if x.wants == dz.API][0]
    assert f.status == "scheduled"
    followups.tick(db)
    assert f.status == "waiting" and "not set up yet" in f.note and posted == []
    monkeypatch.setenv("EKO_ACQUISITION_API_URL", "https://acquisition.example/leads")
    monkeypatch.setenv("EKO_ACQUISITION_API_KEY", "secret")
    followups.tick(db)
    db.expire_all()
    assert [x for x in _followups(db) if x.wants == dz.API][0].status == "sent"
    url, body, headers = posted[0]
    assert url == "https://acquisition.example/leads" and headers["Authorization"] == "Bearer secret"
    assert body["phone"] == PHONE and body["requested_action"].startswith("Assign to DC")
    assert any(s["stage"] == "handed_over" for s in body["journey"])
    assert acquisition_handover.configured()


def test_resolving_with_a_persons_disposition_emails_but_opens_no_new_ticket(db, client, team_mail):
    from src.services import tickets
    tap_campaign(db)
    say(db, "Mere ghar ka pata badalna hai, kya karna hoga?")          # a ticket for the team
    team_mail.clear()
    r = client.post(f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}/attention",
                    json={"needed": False, "disposition": "hold_later"})
    assert r.status_code == 200, r.text
    assert not conv(db).needs_attention and tickets.open_ticket(db, PHONE) is None
    assert len(team_mail) == 1 and "Interested later" in team_mail[0][0]


def test_the_journeys_are_stored_for_sql(db, client):
    from src.models.inbox import LeadJourney, LeadJourneyStep
    from src.services import lead_journey_store
    _upload(db, client)
    try:
        assert lead_journey_store.sync_all(db) == 1
        row = db.get(LeadJourney, PHONE)
        assert row.outcome == "handed_over" and row.furthest_stage == "handed_over"
        assert row.interested_at and row.pin_at and row.uploaded_at and row.handed_over_at
        steps = db.query(LeadJourneyStep).filter(LeadJourneyStep.phone == PHONE).order_by(LeadJourneyStep.seq).all()
        assert len(steps) == row.steps_count and "handed_over" in {x.key for x in steps}
        # Refreshing again replaces the steps rather than adding to them.
        lead_journey_store.sync_all(db)
        assert db.query(LeadJourneyStep).filter(LeadJourneyStep.phone == PHONE).count() == row.steps_count
    finally:
        db.query(LeadJourneyStep).delete()
        db.query(LeadJourney).delete()
        db.commit()


def test_submit_all_sends_every_nudge_only_when_pressed(db, client, monkeypatch):
    from src.services import nudge_templates
    sent = []
    monkeypatch.setattr(nudge_templates, "submit", lambda db, purpose, by: sent.append((purpose, by)) or [])
    r = client.post("/api/v1/inbox/dispositions/nudge-templates/submit-all")
    assert r.status_code == 200
    assert [p for p, _ in sent] == list(nudge_messages.PURPOSES) and {b for _, b in sent} == {"admin@eko.co.in"}


def test_a_nudge_meta_filed_as_marketing_goes_in_as_marketing_in_every_language(db, monkeypatch):
    from src.services import nudge_templates, whatsapp_service
    asked = []

    def fake_submit(self, template, category="MARKETING"):
        asked.append(category)
        if category == "UTILITY" and len(asked) > 1:
            return {"status": "failed", "error": "Template category doesn't match: The category UTILITY doesn't match "
                                                 "the one that's already associated with this template, MARKETING."}
        template.status = "PENDING"
        template.category = category
        return {"status": "success"}

    monkeypatch.setattr(whatsapp_service.WhatsAppTemplateSubmissionService, "submit", fake_submit)
    out = nudge_templates.submit(db, "more_info", "admin@eko.co.in")
    assert all(r["status"] == "PENDING" and not r.get("error") for r in out)
    assert asked[:3] == ["UTILITY", "UTILITY", "MARKETING"]


@pytest.mark.parametrize("typed,step", [
    ("13", "AWAIT_INVEST"), ("12 th", "AWAIT_INVEST"), ("ધોરણ ૧૨", "AWAIT_INVEST"), ("BCom", "AWAIT_INVEST"),
    ("बारहवीं पास", "AWAIT_INVEST"), ("10th pass", "NOT_ELIGIBLE"), ("I am interested", "AWAIT_EDUCATION"),
])
def test_an_education_typed_in_their_own_words_moves_on(db, typed, step):
    tap_campaign(db, lang="gu")
    say(db, SERVED_PIN)
    say(db, typed)
    assert conv(db).bot_step == step


def test_cannot_invest_offers_the_lower_investment_option_and_tells_the_team(db, client, team_mail):
    from src.services import tickets
    tap_campaign(db)
    say(db, SERVED_PIN)
    qualify(db)
    tap(db, "invest:no")
    c = conv(db)
    assert c.bot_step == onboarding_bot.NOT_INVESTING
    body = StubMeta.sent[-1][2]
    assert body == bot_messages.MESSAGES["en"]["not_investing"] and "lower-investment" in body
    # Recorded as the sheet's "Investment issue": the bot first (no ticket or email since the
    # user's sheet of 23 Oct), and the reply counts as the nudge, so nothing more is sent now.
    assert c.disposition == "ni_investment" and tickets.open_ticket(db, PHONE) is None and team_mail == []
    nudge = [f for f in _followups(db) if f.purpose == "lower_investment"]
    assert len(nudge) == 1 and nudge[0].status == "sent" and nudge[0].note == "Said in the bot's reply"
    assert StubMeta.sent[-1][2] == body


# --- Open action items on a lead, and the missing-step alert (2026-10-22) -----

def test_a_leads_open_action_items_list_everything_still_to_do(db, client):
    tap_campaign(db)
    say(db, "Mere ghar ka pata badalna hai, kya karna hoga?")       # a question for the team
    _record(client, "lang_barrier")                                # a nudge now and a task for the team
    _record(client, "hold_later", at=(inbox.now() + __import__("datetime").timedelta(days=5)).isoformat())
    j = client.get(f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}/journey").json()
    kinds = {o["kind"] for o in j["open"]}
    assert {"ticket", "task", "nudge"} <= kinds
    assert any("check back" in o["text"] for o in j["open"] if o["kind"] == "nudge")
    row = client.get("/api/v1/inbox/dispositions/journeys").json()[0]
    assert len(row["open"]) == len(j["open"])


def _recipient(db):
    return db.query(WhatsAppCampaignRecipient).filter(WhatsAppCampaignRecipient.phone == PHONE).one()


def test_a_reply_to_a_campaign_never_sent_is_flagged(db, client):
    tap_campaign(db)
    checks = {f["check"] for f in client.get("/api/v1/inbox/journeys/missing-steps").json()["flags"]}
    assert "replied_not_sent" in checks
    r = _recipient(db)
    r.sent_at = inbox.now()
    db.commit()
    checks = {f["check"] for f in client.get("/api/v1/inbox/journeys/missing-steps").json()["flags"]}
    assert "replied_not_sent" not in checks


def test_read_with_no_delivered_update_is_flagged(db, client):
    r = _recipient(db)
    r.sent_at, r.read_at = inbox.now(), inbox.now()
    db.commit()
    out = client.get("/api/v1/inbox/journeys/missing-steps").json()
    assert [f["check"] for f in out["flags"]] == ["read_not_delivered"] and out["leads"] == 1


def test_documents_without_the_answers_or_the_hand_over_are_flagged(db, client):
    tap_campaign(db)
    _recipient(db).sent_at = inbox.now()
    c = conv(db)
    c.documents_submitted_at = inbox.now()
    db.commit()
    flags = {f["check"]: f for f in client.get("/api/v1/inbox/journeys/missing-steps").json()["flags"]}
    assert "docs_without_answers" in flags and "PIN code" in flags["docs_without_answers"]["detail"]
    assert "handover_not_queued" in flags


def test_a_journey_that_went_by_the_book_has_no_flags(db, client):
    _recipient(db).sent_at = inbox.now()
    db.commit()
    _upload(db, client)
    c = conv(db)
    from src.services import followups
    followups.hand_over(db, c)
    db.commit()
    assert client.get("/api/v1/inbox/journeys/missing-steps").json()["flags"] == []


def _checks(client):
    return {f["check"]: f for f in client.get("/api/v1/inbox/journeys/missing-actions").json()["flags"]}


def test_the_missing_step_alert_keeps_to_its_record_checks(db, client):
    from datetime import timedelta
    tap_campaign(db)
    say(db, SERVED_PIN)
    c = conv(db)
    c.last_inbound_at = inbox.now() - timedelta(days=4)               # also a missing disposition
    db.commit()
    steps = client.get("/api/v1/inbox/journeys/missing-steps").json()
    assert {f["group"] for f in steps["flags"]} == {"record"} and "replied_not_sent" in {f["check"] for f in steps["flags"]}
    actions = client.get("/api/v1/inbox/journeys/missing-actions").json()
    assert {f["group"] for f in actions["flags"]} <= {"disposition", "action"}
    assert "quiet_no_outcome" in {f["check"] for f in actions["flags"]}


def test_a_chat_the_team_handled_without_recording_an_outcome_is_flagged(db, client):
    from datetime import timedelta
    tap_campaign(db)
    _recipient(db).sent_at = inbox.now()
    db.add(WhatsAppMessage(message_id=uuid.uuid4().hex, phone=PHONE, direction="OUT", kind="text", body="Hello",
                           status="SENT", sent_by="kavya.shukla@eko.co.in", created_at=inbox.now() - timedelta(hours=3)))
    db.commit()
    flagged = _checks(client)["no_outcome_after_team"]
    assert flagged["group"] == "disposition"
    _record(client, "int_more_info")
    assert "no_outcome_after_team" not in _checks(client)


def test_a_lead_gone_quiet_in_the_bots_questions_without_an_outcome_is_flagged(db, client):
    from datetime import timedelta
    tap_campaign(db)
    say(db, SERVED_PIN)
    c = conv(db)
    c.last_inbound_at = inbox.now() - timedelta(days=4)
    db.commit()
    assert "quiet_no_outcome" in _checks(client)
    _record(client, "rnr_no_answer")
    assert "quiet_no_outcome" not in _checks(client)


def test_overdue_and_missing_action_items_are_flagged(db, client):
    from datetime import timedelta
    from src.models.inbox import FollowUp
    tap_campaign(db)
    _record(client, "lang_barrier")                       # a task for the team, and a nudge
    for f in _followups(db):
        f.created_at = inbox.now() - timedelta(days=3)
        if f.wants != dz.TASK:
            f.status, f.due_at = "scheduled", inbox.now() - timedelta(hours=2)
    db.commit()
    checks = _checks(client)
    assert {"task_overdue", "nudge_overdue"} <= set(checks) and checks["task_overdue"]["group"] == "action"
    # A disposition whose action item was never set up (e.g. recorded before follow-ups existed).
    db.query(FollowUp).delete()
    db.commit()
    assert "action_not_set_up" in _checks(client)


def test_a_question_left_for_more_than_a_day_is_flagged(db, client):
    from datetime import timedelta
    tap_campaign(db)
    say(db, "Mere ghar ka pata badalna hai, kya karna hoga?")
    t = db.query(AttentionTicket).filter(AttentionTicket.phone == PHONE).one()
    t.raised_at = inbox.now() - timedelta(days=2)
    db.commit()
    assert "ticket_overdue" in _checks(client)


def test_each_disposition_shows_its_action_items_done_planned_and_missed_with_owners(db, client, team_mail):
    from datetime import timedelta
    tap_campaign(db)
    say(db, "Abhi paisa nahi hai mere paas")
    _record(client, "busy_at_time", at=(inbox.now() + timedelta(hours=3)).isoformat())   # confirm now, call back later
    j = client.get(f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}/journey").json()
    now_block = j["dispositions"][0]
    assert now_block["current"] and now_block["label"] == "Call at specific time" and now_block["sheet_owner"] == "Bot"
    by_status = {i["status"]: i for i in now_block["items"]}
    assert by_status["done"]["owner_label"] == "Bot" and "confirm" in by_status["done"]["text"]
    assert by_status["planned"]["text"].startswith("WhatsApp message to get back")
    # A human-owned disposition: the team is told; an overdue nudge counts as missed.
    _record(client, "hold_financial", at=(inbox.now() - timedelta(days=2)).isoformat())
    for f in _followups(db):
        if f.purpose == "checking_in":
            f.status = "scheduled"
    db.commit()
    j = client.get(f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}/journey").json()
    block = j["dispositions"][0]
    assert block["label"] == "Financial constraint currently" and block["sheet_owner"] == "Bot"
    statuses = {(i["owner"], i["status"]) for i in block["items"]}
    assert ("human", "done") in statuses and ("bot", "missed") in statuses
    team = next(i for i in block["items"] if i["owner"] == "human")
    assert team["owner_label"].startswith("Team: ") and "Kavya Shukla" in team["owner_label"]
    assert j["dispositions"][1]["label"] == "Call at specific time" and not j["dispositions"][1]["current"]
    row = client.get("/api/v1/inbox/dispositions/journeys").json()[0]
    assert row["actions"]["missed"] >= 1 and row["actions"]["done"] >= 2


def test_a_lead_nobody_has_recorded_shows_the_bots_disposition_and_what_it_did(db, client):
    tap_campaign(db)
    j = client.get(f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}/journey").json()
    [only] = j["dispositions"]
    assert only["recorded_by"] == "Bot" and only["label"] == "Interested: in the bot's questions" and only["current"]
    assert any(i["owner_label"] == "Bot" and i["status"] == "done" for i in only["items"])


def test_the_bots_dispositions_come_before_the_teams_with_their_actions(db, client):
    # Arshad's case: through the bot to the upload link, then the team records "Other: trust issue".
    tap_campaign(db)
    say(db, SERVED_PIN)
    qualify(db)
    tap(db, "invest:yes")
    tap(db, "docs:yes")
    _record(client, "other", note="Trust issue")
    j = client.get(f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}/journey").json()
    labels = [b["label"] for b in j["dispositions"]]
    assert labels == ["Other", "Documents pending", "Interested: in the bot's questions"]
    now, docs, interested = j["dispositions"]
    assert now["current"] and now["recorded_by"] == "Admin" and now["note"] == "Trust issue"
    assert docs["recorded_by"] == "Bot" and any("upload link" in i["text"] for i in docs["items"])
    texts = " | ".join(i["text"] for i in interested["items"])
    assert "Asked for their PIN code" in texts and "Asked about their education" in texts



def test_kavya_is_emailed_only_when_a_chat_goes_to_a_person(monkeypatch):
    # Escalations and a person's action go to the admin and Kavya; the news that
    # someone tapped Interested, asked for guidance or uploaded documents, to the admin alone.
    from src.services import notifier
    sent = []
    monkeypatch.setattr(notifier, "_send", lambda to, subject, body: sent.append((subject, to)) or True)
    monkeypatch.setattr(notifier, "NOTIFY_ALSO", "kavya.shukla@eko.co.in")
    notifier.notify_button_click("mansi@eko.co.in", {"name": "Ravi", "phone": "+919000000001", "button_text": "Interested"})
    notifier.notify_webinar("mansi@eko.co.in", {"name": "Ravi", "phone": "+919000000001", "answer": "yes"})
    notifier.notify_documents_submitted("mansi@eko.co.in", {"name": "Ravi", "phone": "+919000000001", "documents": []})
    notifier.notify_attention("mansi@eko.co.in", {"person": {"name": "Ravi", "phone": "+919000000001"},
                                                  "attention": {"reason": "asked a question"}}, "text", "url")
    notifier.notify_team("mansi@eko.co.in", "AutoGMap: Investment issue — Ravi", "body")
    to = [t for _, t in sent]
    assert to[:3] == ["mansi@eko.co.in"] * 3
    assert all("kavya.shukla@eko.co.in" in t for t in to[3:]) and len(to) == 5


def test_a_trust_concern_is_answered_with_the_website_and_goes_to_a_person_to_call(db, emailed):
    from src.services import tickets
    tap_campaign(db, lang="gu")
    say(db, SERVED_PIN)
    qualify(db)
    tap(db, "invest:yes")
    tap(db, "docs:yes")                                      # at the last step: the upload link
    say(db, "Na . મને તમારા પર વિશ્ર્વાસ નથી.  તમે કોઈ  frod hy to")
    body = StubMeta.sent[-1][2]
    assert "Eko Bharat Ventures" in body
    assert ("અમારી વિશ્વસનીયતા ચકાસવા માટે તમે અમારી વેબસાઇટની મુલાકાત લઈ શકો છો: "
            "https://kiosk.eko.in/?utm_source=AutoGMap&utm_medium=whatsapp&utm_campaign=Delhi%20CSP") in body
    assert "તમે +91 7291988625 પર અમારો સીધો સંપર્ક પણ કરી શકો છો (કૉલ/WhatsApp)." in body
    c = conv(db)
    # Recorded as "Trust concern" (Interested). The team is not told yet: the ticket and the
    # email go two hours on, an hour after the bot's reminder (the user, 2026-10-23).
    from datetime import timedelta
    from src.services import dispositions as dz, followups, lead_journey
    assert c.disposition == "int_trust" and c.disposition_by == "bot" and dz.category_of("int_trust").key == "interested"
    assert not c.needs_attention and tickets.open_ticket(db, PHONE) is None and emailed == []
    esc = [f for f in _followups(db) if f.wants == dz.ESCALATE][0]
    assert abs((inbox.aware(esc.due_at) - inbox.now()) - timedelta(hours=2)) < timedelta(minutes=1)
    followups.tick(db, inbox.now() + timedelta(hours=1))
    assert emailed == []
    followups.tick(db, inbox.now() + timedelta(hours=2, minutes=5))
    c = conv(db)
    assert c.needs_attention and c.attention_reason.startswith("Call this lead: trust concern")
    assert "the last step before their documents" in c.attention_reason
    assert tickets.open_ticket(db, PHONE) is not None and len(emailed) == 1
    block = lead_journey.build(db, c)["dispositions"][0]
    assert block["label"] == "Trust concern" and block["current"]
    items = {i["text"].split(":")[0]: i for i in block["items"]}
    assert items["Answered who Eko is, with the website link and our number to call"]["status"] == "done"
    told = items["Tell the team to call them"]
    assert told["status"] == "done" and told["result"].startswith("Ticket raised; emailed")
    assert "Call them about their trust concern" in items


def test_an_older_trust_concern_shows_from_its_ticket_under_a_later_disposition(db, client):
    # Before the bot recorded it (Arshad, 22 Oct): read from the ticket its trust answer raised,
    # and kept as an earlier disposition when the team recorded "Other" afterwards.
    from src.models.inbox import AttentionTicket
    from src.services import lead_journey
    tap_campaign(db)
    c = conv(db)
    db.add(AttentionTicket(phone=PHONE, question="Call this lead: trust concern. They worry Eko may be fake. "
                                                 "At: Upload link sent. They wrote: “fraud hai kya”.",
                           raised_at=inbox.now() - __import__("datetime").timedelta(hours=3)))
    db.commit()
    _record(client, "other", note="Trust issue")
    blocks = lead_journey.build(db, conv(db))["dispositions"]
    assert blocks[0]["label"] == "Other" and blocks[0]["current"]
    trust = next(b for b in blocks if b["key"] == "int_trust")
    assert trust["recorded_by"] == "Bot" and trust["note"].startswith("They worry Eko may be fake")
    statuses = {i["text"].split(":")[0]: i["status"] for i in trust["items"]}
    assert statuses["Call them about their trust concern"] == "planned"


DISTRUST = "Na . મને તમારા પર વિશ્ર્વાસ નથી.  તમે કોઈ  frod hy to"


def test_a_trust_concern_at_the_documents_question_ends_with_the_upload_line_and_link(db, emailed):
    tap_campaign(db, lang="gu")
    say(db, SERVED_PIN)
    qualify(db)
    tap(db, "invest:yes")                                     # now at "are your documents ready?"
    assert conv(db).bot_step == onboarding_bot.AWAIT_DOCS
    say(db, DISTRUST)
    kind, _to, body, extra = StubMeta.sent[-1]
    assert body.rstrip().endswith(bot_messages.MESSAGES["gu"]["remind_upload"])
    assert kind == "link" and conv(db).upload_token in extra["url"]
    assert conv(db).bot_step == onboarding_bot.AWAIT_DOCS        # their Yes or No still counts


def test_a_trust_concern_at_an_earlier_step_has_no_upload_line(db, emailed):
    tap_campaign(db, lang="gu")
    say(db, SERVED_PIN)                                       # now at the education question
    say(db, DISTRUST)
    body = StubMeta.sent[-1][2]
    assert "Eko Bharat Ventures" in body and "kiosk.eko.in" in body
    assert bot_messages.MESSAGES["gu"]["remind_upload"] not in body
    # Still goes to a person: two hours on, an hour after the bot's reminder.
    from src.services import dispositions as dz
    assert conv(db).disposition == "int_trust" and [f for f in _followups(db) if f.wants == dz.ESCALATE]


def test_whats_next_shows_the_wait_the_reminder_and_the_next_disposition(db, client):
    tap_campaign(db)
    say(db, SERVED_PIN)
    qualify(db)
    tap(db, "invest:yes")
    tap(db, "docs:yes")                                       # the upload link is out
    j = client.get(f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}/journey").json()
    texts = [n["text"] for n in j["whats_next"]]
    assert "Waiting for them to upload their documents" in texts
    assert "Reminder with the same question, if they stay quiet" in texts
    assert any(t.startswith("Next disposition: Physical visit required: handed to Eko Acquisition") for t in texts)


def test_whats_next_says_when_nothing_is_planned(db, client):
    tap_campaign(db)
    from src.models.inbox import WhatsAppConversation as C
    c = conv(db)
    c.bot_step = None
    db.commit()
    _record(client, "other", note="Trust issue")
    nxt = client.get(f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}/journey").json()["whats_next"]
    assert [n["kind"] for n in nxt] == ["none"]


def test_the_upload_link_records_documents_pending_with_the_sheets_follow_up(db, client):
    tap_campaign(db)
    say(db, SERVED_PIN)
    qualify(db)
    tap(db, "invest:yes")
    tap(db, "docs:yes")
    c = conv(db)
    assert c.disposition == "int_docs_pending" and c.disposition_by == "bot"
    reminders = sorted((f for f in _followups(db) if f.purpose == "docs_reminder"), key=lambda f: f.due_at)
    assert [f.status for f in reminders] == ["sent", "scheduled"]       # the link now, a reminder in 2 days
    assert reminders[0].note == "Said in the bot's reply"
    # Sending the link again (a second "Yes") does not record it twice.
    tap(db, "docs:yes")
    assert len([f for f in _followups(db) if f.purpose == "docs_reminder"]) == 2
    # Uploading cancels the reminder.
    c = conv(db)
    c.documents_submitted_at = inbox.now()
    db.commit()
    followups.tick(db)
    db.expire_all()
    assert all(f.status != "scheduled" for f in _followups(db) if f.purpose == "docs_reminder")


def test_outside_our_area_carries_on_to_the_end_with_nothing_closed(db, monkeypatch, team_mail):
    # They go through the whole journey; nothing is recorded as rejected and nobody is emailed.
    from src.services import lead_journey, tickets
    monkeypatch.setattr(pincode_coverage, "_locate_or_none", lambda pin: (19.07, 72.87))  # Mumbai: not served
    tap_campaign(db)
    say(db, "400001")
    qualify(db)
    tap(db, "invest:yes")
    tap(db, "docs:yes")
    c = conv(db)
    assert c.bot_step == onboarding_bot.AWAIT_UPLOAD and c.upload_token
    assert c.disposition == "int_docs_pending" and tickets.open_ticket(db, PHONE) is None and team_mail == []
    assert not [f for f in _followups(db) if f.purpose == "other_options"]
    pin = next(s for s in lead_journey.build(db, c)["steps"] if s["key"] == "pin")
    assert "not qualified for SBI branch code" in pin["what"] and pin["tone"] == "neutral"
    # Not a rejection: an Interested disposition of its own, before the documents.
    from src.services import dispositions as dz, handover
    blocks = lead_journey.build(db, c)["dispositions"]
    assert "int_not_sbi" in [b["key"] for b in blocks]
    assert dz.category_of("int_not_sbi").key == "interested" and dz.normalise("rej_outside_area") == "int_not_sbi"
    c.bot_step, c.disposition = onboarding_bot.AWAIT_EDUCATION, None
    assert handover.bot_disposition(c) == "int_not_sbi"


def test_education_below_12th_is_still_a_polite_no_with_nothing_more(db, team_mail):
    tap_campaign(db)
    say(db, SERVED_PIN)
    qualify(db, "other")
    c = conv(db)
    assert c.bot_step == onboarding_bot.NOT_ELIGIBLE and c.disposition is None and team_mail == []


# --- Action items queue, outcomes, disposition mix (2026-10-22) ---------------

def test_marking_a_task_done_needs_an_outcome(db, client):
    tap_campaign(db)
    _record(client, "lang_barrier")                       # a task for the team
    task = next(f for f in _followups(db) if f.wants == dz.TASK)
    url = f"/api/v1/inbox/followups/{task.followup_id}/done"
    assert client.post(url, json={}).status_code == 422
    assert client.post(url, json={"outcome": "Sorted it"}).status_code == 422
    db.refresh(task)
    assert task.status in followups.PENDING
    r = client.post(url, json={"outcome": "Spoke to them", "note": "Moved to the Gujarati caller"})
    assert r.status_code == 200, r.text
    db.refresh(task)
    assert task.status == "done" and task.done_by == "admin@eko.co.in"
    assert task.note == "Spoke to them: Moved to the Gujarati caller"


def test_the_action_queue_sorts_open_items_by_when_and_owner(db, client):
    tap_campaign(db)
    _record(client, "lang_barrier")                       # a task for the team, and a nudge
    fs = _followups(db)
    task = next(f for f in fs if f.wants == dz.TASK)
    task.created_at = inbox.now() - timedelta(days=3)     # open 3 days: overdue, as the Dashboard alert says
    nudge = next(f for f in fs if f.wants != dz.TASK)
    nudge.status, nudge.due_at = "scheduled", inbox.now() + timedelta(days=3)
    db.add(AttentionTicket(phone=PHONE, question="Is this real?", raised_at=inbox.now()))
    db.commit()

    q = client.get("/api/v1/inbox/followups/queue").json()
    ids = {b: {i["id"] for i in q[b]} for b in ("overdue", "today", "upcoming")}
    assert task.followup_id in ids["overdue"] and nudge.followup_id in ids["upcoming"]
    ticket = next(i for i in q["today"] if i["source"] == "ticket")
    assert ticket["owner"] == "human" and ticket["owner_label"].startswith("Team: ") and not ticket["can_mark_done"]
    overdue_task = next(i for i in q["overdue"] if i["id"] == task.followup_id)
    assert overdue_task["can_mark_done"] and overdue_task["owner_type"] == "Team"
    assert "Spoke to them" in q["outcomes"]

    bot = client.get("/api/v1/inbox/followups/queue?owner=bot").json()
    mine = [i for b in ("overdue", "today", "upcoming") for i in bot[b]]
    assert mine and all(i["owner"] == "bot" for i in mine) and nudge.followup_id in {i["id"] for i in mine}
    assert {o["key"]: o["count"] for o in bot["owners"]}["human"] >= 2   # counts stay for every owner


def test_the_teams_test_numbers_stay_out_of_the_action_queue(db, client):
    tap_campaign(db)
    _record(client, "lang_barrier")
    cid = uuid.uuid4().hex
    db.add(WhatsAppCampaign(campaign_id=cid, name="Test send", data_source_type="upload", status="COMPLETED",
                            total_contacts=2))
    db.add(WhatsAppCampaignRecipient(recipient_id=uuid.uuid4().hex, campaign_id=cid, phone=PHONE, status="READ"))
    db.commit()
    q = client.get("/api/v1/inbox/followups/queue").json()
    assert not (q["overdue"] or q["today"] or q["upcoming"])


def test_the_disposition_mix_by_campaign_template_and_state(db, client):
    from src.models import Business
    tap_campaign(db)
    _record(client, "lang_barrier")
    base = _recipient(db)
    base.sent_at = inbox.now() - timedelta(days=1)
    db.add(WhatsAppTemplate(template_id="t1", name="csp_gujarati", body="Hello {{name}}", status="APPROVED"))
    db.query(WhatsAppCampaign).filter(WhatsAppCampaign.campaign_id == base.campaign_id).one().template_id = "t1"
    db.add(Business(business_id="B1", job_id="J1", name="Patel Xerox", phone=PHONE, category="Copy shop",
                    state="Gujarat", source_query="q", dedup_key="k1"))
    db.add(WhatsAppCampaignRecipient(recipient_id=uuid.uuid4().hex, campaign_id=base.campaign_id,
                                     phone="+919000000002", status="DELIVERED", sent_at=inbox.now()))
    test_id = uuid.uuid4().hex                             # a test send: left out
    db.add(WhatsAppCampaign(campaign_id=test_id, name="Test send", data_source_type="upload", status="COMPLETED",
                            total_contacts=2))
    db.add(WhatsAppCampaignRecipient(recipient_id=uuid.uuid4().hex, campaign_id=test_id,
                                     phone="+919000000003", status="READ", sent_at=inbox.now()))
    db.commit()

    mix = client.get("/api/v1/whatsapp/insights/dispositions").json()
    assert [r["value"] for r in mix["campaign"]] == ["Delhi CSP"]
    row = mix["campaign"][0]
    assert row["sent"] == 2 and row["replied"] == 1
    assert row["groups"]["follow_up"] == 1 and row["groups"]["no_reply"] == 1
    labels = {d["label"]: d["count"] for d in row["dispositions"]}
    assert labels == {dz.label("lang_barrier"): 1, "No reply yet": 1}
    assert [r["value"] for r in mix["template"]] == ["csp_gujarati"]
    states = {r["value"]: r for r in mix["state"]}
    assert states["Gujarat"]["groups"]["follow_up"] == 1 and states["Unknown"]["groups"]["no_reply"] == 1


def test_messages_whatsapp_does_not_pass_on_say_what_they_can_be():
    kind, body, payload = inbox.describe_inbound({"type": "unsupported", "errors": [
        {"code": 131051, "title": "Message type unknown", "error_data": {"details": "Message type is currently not supported."}}]})
    assert kind == "unsupported" and body == inbox.UNSUPPORTED_TEXT
    assert payload == {"code": 131051, "reason": "Message type is currently not supported."}


def test_contact_cards_forms_and_newer_types_show_what_they_hold():
    _, body, _ = inbox.describe_inbound({"type": "contacts", "contacts": [
        {"name": {"formatted_name": "Ravi Patel"}, "phones": [{"phone": "+91 98765 43210"}]}]})
    assert body == "[Contact card] Ravi Patel, +91 98765 43210"
    _, body, payload = inbox.describe_inbound({"type": "interactive", "interactive": {
        "type": "nfm_reply", "nfm_reply": {"response_json": '{"flow_token": "x", "pin": "110001"}'}}})
    assert body == "[Form reply] pin: 110001" and payload == {"form": {"pin": "110001"}}
    assert inbox.describe_inbound({"type": "request_welcome"})[1] == "[Opened a chat with us for the first time]"
    kind, body, payload = inbox.describe_inbound({"type": "something_brand_new_from_meta", "x": 1})
    assert len(kind) <= 20 and "cannot show yet" in body and payload["raw"]["x"] == 1


# --- The bot reads the disposition from a reply (the user's sheet, 2026-10-23) ---

def test_a_reply_with_a_time_is_a_call_at_that_time(db, team_mail):
    from src.services import reply_dispositions
    tap_campaign(db)
    say(db, SERVED_PIN)
    qualify(db)                                     # at the investment question
    say(db, "Abhi busy hoon, shaam 5 baje call karna")
    c = conv(db)
    assert c.disposition == "busy_at_time" and c.disposition_by == "bot" and c.bot_step == onboarding_bot.AWAIT_INVEST
    due = [f for f in _followups(db) if f.purpose == "callback_due"][0]
    assert inbox.aware(due.due_at).astimezone(reply_dispositions.IST).hour == 17
    assert StubMeta.sent[-1][2] == nudge_messages.text("callback_confirm", nudge_messages.HINGLISH)
    assert team_mail == []


def test_an_answer_to_the_bots_question_is_not_read_as_a_disposition(db):
    tap_campaign(db)
    say(db, SERVED_PIN)
    qualify(db)
    say(db, "nahi")                                 # a No to "can you invest?"
    c = conv(db)
    assert c.bot_step == onboarding_bot.NOT_INVESTING and c.disposition == "ni_investment"


def test_a_question_is_left_for_the_faq_not_read_as_a_disposition(db):
    tap_campaign(db)
    say(db, "Kya main baad mein apply kar sakta hoon?")
    assert conv(db).disposition is None


def test_not_interested_closes_with_the_sheets_message(db, client):
    tap_campaign(db)
    say(db, SERVED_PIN)
    say(db, "Galti se apply ho gaya tha, mujhe iski zaroorat nahi hai")
    c = conv(db)
    assert c.disposition == "ni_mistake"
    assert StubMeta.sent[-1][2] == nudge_messages.text("closing_polite", nudge_messages.HINGLISH)
    assert not [f for f in _followups(db) if f.status in ("scheduled", "waiting")]
    say(db, "Abhi interested nahi hoon")
    assert conv(db).disposition == "ni_currently"
    assert StubMeta.sent[-1][2] == nudge_messages.text("closing_later", nudge_messages.HINGLISH)


def test_wrong_number_and_existing_csp_get_their_closing_messages(db):
    tap_campaign(db)
    say(db, "wrong number")
    assert conv(db).disposition == "inv_incorrect"
    assert StubMeta.sent[-1][2] == nudge_messages.text("closing_sorry", "en")
    say(db, "I am already a CSP with Eko, already running a CSP")
    assert conv(db).disposition == "dup_existing"
    assert StubMeta.sent[-1][2] == nudge_messages.text("already_with_us", "en")


def test_a_later_date_is_noted_and_the_team_is_told(db, team_mail):
    tap_campaign(db)
    say(db, "Diwali ke baad dekhenge, next month karunga")
    c = conv(db)
    assert c.disposition == "hold_later" and len(team_mail) == 1
    check = [f for f in _followups(db) if f.purpose == "checking_in"][0]
    assert (inbox.aware(check.due_at) - inbox.now()).days >= 28
    # Nothing goes out until that date, so they hear it is noted now.
    assert StubMeta.sent[-1][2] == nudge_messages.text("callback_confirm", nudge_messages.HINGLISH)


def test_no_hourly_reminder_after_they_said_where_they_stand(db):
    from datetime import timedelta
    from src.services import nudges
    tap_campaign(db)
    say(db, SERVED_PIN)
    say(db, "busy hoon abhi, baad mein call karna")
    c = conv(db)
    assert c.disposition == "busy_later"
    assert not nudges.due(db, c, inbox.now() + timedelta(hours=2))


def test_the_rules_read_the_common_replies():
    from datetime import datetime, timezone
    from src.services.reply_dispositions import detect
    now = datetime(2026, 10, 23, 6, 0, tzinfo=timezone.utc)      # 11:30 IST
    cases = {
        "mere papa ka number hai": "ndm_not_applicant",
        "meri cibil kharab hai": "rej_credit",
        "paise nahi hai abhi": "hold_financial",
        "nahi chahiye": "ni_no_requirement",
        "maine apply nahi kiya": "inv_denied",
        "pehle hi apply kar diya hai": "dup_in_process",
        "samajh nahi aaya": "lang_barrier",
        "call me": "int_callback",
        "15 nov ke baad baad mein dekhenge": "hold_after_date",
        "मैं अभी व्यस्त हूँ": "busy_busy",
        "hello": None, "ok thanks": None, "haan": None,
    }
    for text, want in cases.items():
        got = detect(text, now)
        assert (got[0] if got else None) == want, text
    key, at = detect("kal 11 am call karna", now)
    assert key == "busy_at_time" and at == datetime(2026, 10, 24, 5, 30, tzinfo=timezone.utc)



def test_every_ticket_and_email_to_the_team_shows_under_the_disposition_of_the_time(db, client, emailed):
    # Arshad's case: the bot handed a question to the team after the upload link; the team
    # recorded "Other" later. The email shows under "Documents pending", where it happened.
    from src.services import lead_journey
    tap_campaign(db)
    say(db, SERVED_PIN)
    qualify(db)
    tap(db, "invest:yes")
    tap(db, "docs:yes")
    say(db, "Mere ghar ka pata badalna hai, kya karna hoga?")
    assert len(emailed) == 1
    _record(client, "other", note="Trust issue")
    blocks = lead_journey.build(db, conv(db))["dispositions"]
    assert blocks[0]["label"] == "Other"
    docs = next(b for b in blocks if b["label"] == "Documents pending")
    told = [i for i in docs["items"] if i["text"].startswith("Handed to the team: ticket and email to")]
    assert len(told) == 1 and "Kavya Shukla" in told[0]["text"] and told[0]["status"] == "done"
    assert "Mere ghar ka pata badalna hai" in told[0]["result"] and told[0]["result"].endswith("· open")


# --- Agent telemetry and quality (the team's blueprint, 2026-10-26) -------------

def _runs(db, agent):
    from src.models.agent_runs import AgentRun
    return db.query(AgentRun).filter(AgentRun.agent == agent).order_by(AgentRun.created_at).all()


def test_edit_distance_is_levenshtein():
    from src.services import agent_telemetry as t
    assert t.levenshtein("kitten", "sitting") == 3 and t.levenshtein("", "abc") == 3 and t.levenshtein("same", "same") == 0


def test_an_faq_answer_is_logged_with_its_context_and_accepted_when_nobody_steps_in(db):
    from datetime import timedelta
    from src.services import agent_telemetry
    tap_campaign(db)
    say(db, "Apply karne ki fees kitni hai?")
    [run] = _runs(db, "bot_faq")
    assert run.prompt == "Apply karne ki fees kitni hai?" and run.output and run.outcome == "pending"
    assert run.context and run.context[0]["source"] == "faq" and run.context_tokens > 0
    agent_telemetry.settle(db, inbox.now() + timedelta(hours=3))
    assert run.outcome == "accepted" and run.edit_distance == 0


def test_an_faq_answer_a_person_had_to_follow_up_counts_as_corrected(db, client):
    from datetime import timedelta
    from src.services import agent_telemetry
    tap_campaign(db)
    say(db, "Apply karne ki fees kitni hai?")
    r = client.post(f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}/messages", json={"message": "Bilkul free hai ji"})
    assert r.status_code == 200, r.text
    agent_telemetry.settle(db, inbox.now() + timedelta(hours=3))
    [run] = _runs(db, "bot_faq")
    assert run.outcome == "edited" and run.final_output == "Bilkul free hai ji" and run.edit_distance > 0


def test_a_reply_disposition_is_judged_by_the_teams_own(db, client):
    tap_campaign(db)
    say(db, "busy hoon abhi")
    [run] = _runs(db, "bot_reply_disposition")
    assert run.output == "busy_busy" and run.context[0] == {**run.context[0], "source": "rule", "text": "busy"}
    _record(client, "busy_later")
    db.refresh(run)
    assert run.outcome == "edited" and run.final_output == "busy_later" and run.finalized_by == "admin@eko.co.in"


def test_a_ready_reply_sent_with_changes_records_the_correction(db, client):
    tap_campaign(db)
    say(db, "hello")
    r = client.post(f"/api/v1/inbox/conversations/{PHONE.lstrip('+')}/messages",
                    json={"message": "Namaste ji, aapka message mil gaya.", "suggested": "Namaste, aapka message mil gaya hai."})
    assert r.status_code == 200, r.text
    [run] = _runs(db, "inbox_ready_reply")
    assert run.outcome == "edited" and run.edit_distance > 0 and run.final_output == "Namaste ji, aapka message mil gaya."


def test_a_template_draft_is_finalized_by_the_reviewers_approval_or_rejection(db, monkeypatch):
    import uuid
    from src.services import agent_telemetry, template_studio, whatsapp_service
    monkeypatch.setattr(whatsapp_service.WhatsAppTemplateSubmissionService, "submit",
                        lambda self, tmpl, category="MARKETING": {"status": "success"})
    drafts = []
    for body in ("Apna business shuru karein", "Eko ke saath kamaai"):
        t = WhatsAppTemplate(template_id=uuid.uuid4().hex, name=f"draft_{len(drafts)}", body=body, language_code="hi",
                             status=template_studio.AWAITING_APPROVAL, origin="agent", generation={})
        db.add(t)
        db.flush()
        agent_telemetry.log(db, "template_writer", "template", t.template_id, body, prompt="write it",
                            context=[agent_telemetry.chunk("facts", "Applying is free")])
        drafts.append(t)
    db.commit()
    drafts[0].body = "Apna khud ka business shuru karein"
    template_studio.approve(db, drafts[0], "kavya@eko.co.in")
    template_studio.reject(db, drafts[1], "kavya@eko.co.in", "Too pushy")
    runs = {r.subject_id: r for r in _runs(db, "template_writer")}
    edited, rejected = runs[drafts[0].template_id], runs[drafts[1].template_id]
    assert edited.outcome == "edited" and edited.edit_distance == len(" khud ka") and edited.finalized_by == "kavya@eko.co.in"
    assert rejected.outcome == "rejected"


def test_the_quality_page_reports_the_blueprints_kpis(db, client):
    from src.services import agent_telemetry
    agent_telemetry.log(db, "inbox_ready_reply", "chat", PHONE, "abc", final_output="abc", finalized_by="x")
    agent_telemetry.log(db, "inbox_ready_reply", "chat", PHONE, "abcd", final_output="abXd", finalized_by="x")
    agent_telemetry.log(db, "template_writer", "template", "t1", None, outcome="failed", error="quota")
    db.commit()
    q = client.get("/api/v1/agents/quality?days=7").json()
    ready = next(a for a in q["agents"] if a["key"] == "inbox_ready_reply")
    assert ready["acceptance_rate"] == 0.5 and ready["avg_edit_distance"] == 0.5
    writer = next(a for a in q["agents"] if a["key"] == "template_writer")
    assert writer["completion_rate"] == 0.0 and writer["failed"] == 1
    assert q["targets"]["acceptance_rate"] == 0.75 and q["weeks"]
    runs = client.get("/api/v1/agents/runs?agent=inbox_ready_reply").json()
    assert len(runs) == 2 and client.get(f"/api/v1/agents/runs/{runs[0]['id']}").json()["id"] == runs[0]["id"]



# --- Agent controls, confidence and clarify (blueprint phase 3, 2026-10-26) ------

def _switch(client, key, on, group="agents"):
    r = client.put(f"/api/v1/agents/controls/{group}/{key}", json={"enabled": on})
    assert r.status_code == 200, r.text
    return r.json()


def test_the_admin_switches_an_agent_off_and_it_is_recorded_who_did(db, client):
    state = _switch(client, "bot_reply_disposition", False)
    row = next(a for a in state["agents"] if a["key"] == "bot_reply_disposition")
    assert row["enabled"] is False and row["changed_by"] == "admin@eko.co.in"
    assert state["history"][0]["what"] == "Bot: dispositions read from replies" and state["history"][0]["on"] is False
    tap_campaign(db)
    say(db, "busy hoon abhi")
    assert conv(db).disposition is None
    _switch(client, "bot_reply_disposition", True)
    say(db, "busy hoon abhi")
    assert conv(db).disposition == "busy_busy"


def test_only_an_admin_may_switch(db, client):
    from src.main import app
    from src.routers.auth import current_user

    class Member:
        email, role = "member@eko.co.in", "manager"
    app.dependency_overrides[current_user] = lambda: Member()
    try:
        r = client.put("/api/v1/agents/controls/agents/bot_faq", json={"enabled": False})
        assert r.status_code == 403
    finally:
        app.dependency_overrides.pop(current_user, None)


def test_faq_answers_off_sends_every_question_to_the_team(db, client):
    _switch(client, "bot_faq", False)
    tap_campaign(db)
    say(db, "Apply karne ki fees kitni hai?")
    c = conv(db)
    assert c.needs_attention and "Applying is free" not in StubMeta.sent[-1][2]
    _switch(client, "bot_faq", True)


def test_a_reply_read_two_ways_is_left_for_a_person_to_clarify(db):
    tap_campaign(db)
    say(db, "busy hoon, not interested")
    c = conv(db)
    assert c.disposition is None and c.needs_attention and c.attention_reason.startswith("Clarify:")
    [run] = _runs(db, "bot_reply_disposition")
    assert run.output == "clarify" and run.evaluation["ambiguous"] == ["ni_currently", "busy_busy"]


def test_a_single_common_word_is_recorded_with_low_confidence(db):
    tap_campaign(db)
    say(db, "busy")
    [run] = _runs(db, "bot_reply_disposition")
    assert conv(db).disposition == "busy_busy" and run.evaluation["confidence"] < 0.75
    assert any(c["name"] == "Confidence" and not c["passed"] for c in run.evaluation["checks"])


def test_template_agents_switched_off_refuse_new_rounds(db, client):
    _switch(client, "template_writer", False)
    r = client.post("/api/v1/whatsapp/studio/generate", json={"state": "Gujarat", "count": 1})
    assert r.status_code == 423 and "turned off" in r.json()["detail"]
    _switch(client, "template_writer", True)


def test_a_context_source_switched_off_is_left_out_of_the_prompt(db, client):
    from src.services import template_studio
    _switch(client, "approved_example", False, "context")
    _switch(client, "past_mistake", False, "context")
    refs, perf, history = template_studio.trimmed_context(db, ["example"], [{"name": "t"}],
                                                          {"mistakes": ["m"], "rejected": [{"angle": "a", "reason": "r"}]})
    assert refs == [] and perf == [{"name": "t"}] and history["mistakes"] == [] and history["rejected"]
    _switch(client, "approved_example", True, "context")
    _switch(client, "past_mistake", True, "context")


def test_ready_replies_switched_off_suggest_nothing(db, client):
    from src.services import chat_summary
    tap_campaign(db)
    _switch(client, "inbox_ready_reply", False)
    assert chat_summary.summarise(db, conv(db))["next"]["reply"] is None
    _switch(client, "inbox_ready_reply", True)


def test_each_source_shows_when_it_was_refreshed(db, client):
    rows = client.get("/api/v1/agents/sources").json()
    keys = {r["key"] for r in rows}
    assert {"tara", "journeys", "approved", "faq", "golden", "runs"} <= keys
    assert all(r["status"] in ("fresh", "stale", "never") for r in rows)


# --- The learning loop (blueprint phase 4, 2026-10-26) ----------------------------

def _gate_passes(monkeypatch, passes=True):
    from src.services import learning_loop
    report = {"total": 31, "passed": 31 if passes else 29,
              "failures": [] if passes else [{"id": "rd-01", "title": "x", "problems": ["broke"]}]}
    monkeypatch.setattr(learning_loop, "_gate", lambda rules: report)


def test_a_reviewers_rewrite_becomes_a_lesson_the_copywriter_is_given(db, client, monkeypatch):
    from src.services import agent_telemetry, learning_loop, template_studio
    agent_telemetry.log(db, "template_writer", "template", "t-1", "Pakki kamaai ka mauka!\nAaj hi apply karein!",
                        final_output="Kamaai ka ek naya mauka!\nAaj hi apply karein!", finalized_by="kavya@eko.co.in")
    db.commit()
    props = client.get("/api/v1/agents/learning").json()["proposals"]
    lesson = next(p for p in props if p["kind"] == "copy_lesson")
    assert "Kamaai ka ek naya mauka" in lesson["after"] and "Pakki" in lesson["before"]
    r = client.post(f"/api/v1/agents/learning/{lesson['id']}/accept")
    assert r.status_code == 200, r.text
    _, _, history = template_studio.trimmed_context(db, [], [], {})
    assert history["accepted_lessons"] and "Kamaai ka ek naya mauka" in history["accepted_lessons"][0]
    assert not [p for p in client.get("/api/v1/agents/learning").json()["proposals"] if p["id"] == lesson["id"]]


def test_a_reply_the_team_read_differently_becomes_a_rule_after_the_golden_gate(db, client, monkeypatch):
    _gate_passes(monkeypatch)
    tap_campaign(db)
    say(db, "busy hoon abhi")
    _record(client, "busy_later")
    rule = next(p for p in client.get("/api/v1/agents/learning").json()["proposals"] if p["kind"] == "rule_phrase")
    assert rule["key"] == "busy_later" and rule["phrase"] == "busy hoon abhi"
    assert client.post(f"/api/v1/agents/learning/{rule['id']}/accept").status_code == 200
    say(db, "busy hoon abhi")
    assert conv(db).disposition == "busy_later" and conv(db).disposition_by == "bot"
    trial = client.post("/api/v1/agents/playground/reply", json={"text": "busy hoon abhi"}).json()
    assert trial["today"]["key"] == "busy_later" and trial["today"]["by"] == "an accepted rule"
    assert client.post(f"/api/v1/agents/learning/{rule['id']}/undo").status_code == 200
    assert client.post("/api/v1/agents/playground/reply", json={"text": "busy hoon abhi"}).json()["today"]["key"] == "busy_busy"


def test_a_rule_that_breaks_the_golden_set_is_refused(db, client, monkeypatch):
    _gate_passes(monkeypatch, passes=False)
    tap_campaign(db)
    say(db, "busy hoon abhi")
    _record(client, "ni_currently")
    rule = next(p for p in client.get("/api/v1/agents/learning").json()["proposals"] if p["kind"] == "rule_phrase")
    r = client.post(f"/api/v1/agents/learning/{rule['id']}/accept")
    assert r.status_code == 409 and r.json()["detail"]["gate"]["failures"][0]["id"] == "rd-01"
    say(db, "busy hoon abhi")
    assert conv(db).disposition == "busy_busy"


def test_a_dismissed_proposal_does_not_come_back(db, client):
    tap_campaign(db)
    say(db, "busy hoon abhi")
    _record(client, "busy_later")
    rule = next(p for p in client.get("/api/v1/agents/learning").json()["proposals"] if p["kind"] == "rule_phrase")
    state = client.post(f"/api/v1/agents/learning/{rule['id']}/dismiss").json()
    assert not [p for p in state["proposals"] if p["id"] == rule["id"]] and state["log"][0]["what"] == "dismissed"


def test_the_playground_writes_two_drafts_side_by_side(db, client, monkeypatch):
    from src.services import learning_loop, template_studio
    from src.services import gemini_client
    seen = []

    def fake_write(client_, prompt, angles, lang):
        seen.append(prompt)
        return [{"body": "with change" if "A CHANGE BEING TRIED" in prompt else "today", "angle": "a", "_errors": []}]
    monkeypatch.setattr(template_studio, "_write_copy", fake_write)
    monkeypatch.setattr(gemini_client, "GeminiClient", lambda *a, **k: object())
    monkeypatch.setattr(learning_loop, "SessionLocal", None, raising=False)
    import src.database as database
    monkeypatch.setattr(database, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    jid = client.post("/api/v1/agents/playground/copy",
                      json={"state": "Gujarat", "instruction": "Mention free training", "without": ["performance"]}).json()["id"]
    job = client.get(f"/api/v1/agents/playground/copy/{jid}").json()
    assert job["status"] == "done", job
    assert job["today"]["body"] == "today" and job["changed"]["body"] == "with change"
    assert "Mention free training" in seen[1] and "Mention free training" not in seen[0]


# --- A shop's own auto-reply to the campaign (the user, 2026-10-26) ----------

ROYAL = ("Hello 👋, Thank you for reaching out to Royal Graphics We specialize in Flex Printing, "
         "Visiting Cards, Vinyl. We will get back to you shortly. Looking forward to serving you! 🙏")


def _templated_campaign(db, sent_at=None):
    from src.services import campaign_buttons
    template_id, campaign_id = uuid.uuid4().hex, uuid.uuid4().hex
    db.add(WhatsAppTemplate(template_id=template_id, name="Gujarat CSP", status="APPROVED",
                            body="Namaste {{name}}, become an SBI CSP with Eko.\n\nApply today: {{link}}",
                            buttons=[{"type": "QUICK_REPLY", "text": "Interested"},
                                     {"type": "QUICK_REPLY", "text": campaign_buttons.webinar_label("en")}]))
    db.add(WhatsAppCampaign(campaign_id=campaign_id, name="Gujarat CSP", data_source_type="scraped",
                            status="COMPLETED", total_contacts=1, template_id=template_id))
    db.add(WhatsAppCampaignRecipient(recipient_id=uuid.uuid4().hex, campaign_id=campaign_id, phone=PHONE,
                                     name="Royal Graphics", status="SENT", provider_message_id="wamid.gj",
                                     tracking_token="tok123", sent_at=sent_at or inbox.now()))
    db.commit()


def test_auto_replies_are_told_from_people():
    from src.services import auto_replies
    assert auto_replies.is_automatic(ROYAL)
    assert auto_replies.is_automatic("નમસ્તે, રોયલ ગ્રાફિક્સ સુધી પહોંચવા બદલ આભાર. અમે તમને ટૂંક સમયમાં સંપર્ક કરીશું.")
    assert auto_replies.is_automatic("We are currently closed. Our business hours are 10am to 7pm.")
    assert not auto_replies.is_automatic("Haan interested hoon, details bhejo")
    assert not auto_replies.is_automatic("Kitna paisa lagega?")
    # Long and within a minute of the campaign: no person typed it.
    now = inbox.now()
    long = "Welcome to Shree Krishna Mobile Repair, all brands, all accessories available here"
    assert auto_replies.is_automatic(long, now, now + timedelta(seconds=8))
    assert not auto_replies.is_automatic(long, now, now + timedelta(minutes=20))


def test_a_shops_auto_reply_gets_the_greeting_with_its_buttons(db):
    _templated_campaign(db)
    say(db, ROYAL)

    kind, _to, body, buttons = StubMeta.sent[-1]
    assert kind == "buttons"
    assert body.startswith("Hello! 👋 Thank you for contacting Eko.")
    assert "SBI Customer Service Point" in body
    assert [b["id"] for b in buttons] == [onboarding_bot.START_INTERESTED, onboarding_bot.START_WEBINAR]
    c = conv(db)
    assert c.bot_step is None and c.needs_attention is False
    # Marked, so Campaign insights does not count it as them replying.
    last_in = (db.query(WhatsAppMessage).filter(WhatsAppMessage.direction == "IN")
               .order_by(WhatsAppMessage.created_at.desc()).first())
    assert last_in.payload["auto_reply"] is True
    # Their bot answering again is not answered again: two bots never loop.
    before = len(StubMeta.sent)
    say(db, ROYAL)
    assert len(StubMeta.sent) == before
    # A tap on the resent button starts the questions as the campaign's would.
    tap(db, onboarding_bot.START_INTERESTED)
    assert conv(db).bot_step is not None


def test_a_campaign_chat_is_never_shown_as_an_enquiry_of_their_own(db):
    from src.services import handover
    _templated_campaign(db)
    say(db, ROYAL)
    assert handover.bot_disposition(conv(db)) == "other"


def test_a_person_answering_the_campaign_is_not_taken_for_a_bot(db):
    _templated_campaign(db, sent_at=inbox.now() - timedelta(hours=3))
    say(db, "hello, what is this about")
    assert conv(db).bot_data.get("auto_reply_for") is None
    last_in = (db.query(WhatsAppMessage).filter(WhatsAppMessage.direction == "IN")
               .order_by(WhatsAppMessage.created_at.desc()).first())
    assert not (last_in.payload or {}).get("auto_reply")


def test_an_auto_reply_while_the_send_is_still_being_saved_counts_as_a_campaigns(db):
    campaign_id = uuid.uuid4().hex
    other = "+919812345670"
    db.add(WhatsAppCampaign(campaign_id=campaign_id, name="Live", data_source_type="scraped",
                            status="RUNNING", total_contacts=1))
    db.add(WhatsAppCampaignRecipient(recipient_id=uuid.uuid4().hex, campaign_id=campaign_id,
                                     phone=other, status="PROCESSING"))
    db.commit()
    assert inbox.from_campaign(db, other) is False
    assert inbox.being_sent(db, other) is True


def test_auto_replies_missed_earlier_are_found_and_answered_once(db):
    from src.services import auto_replies
    _templated_campaign(db)
    # Came in before the bot knew: recorded, but not answered.
    inbox.record_inbound(db, {"from": PHONE.lstrip("+"), "id": "wamid.royal", "type": "text",
                              "text": {"body": ROYAL}}, "Royal Graphics")
    db.commit()
    found = auto_replies.missed(db)
    assert [c.phone for c, _m in found] == [PHONE]
    conv_, msg = found[0]
    onboarding_bot.handle(db, conv_, msg)
    db.commit()
    assert StubMeta.sent[-1][0] == "buttons"
    assert auto_replies.missed(db) == []


def test_the_playground_says_what_the_bot_does_not_only_the_disposition(client):
    # "Invest" is no disposition, but the bot answers it from the FAQ (the user, 2026-10-26).
    def bot(text):
        return client.post("/api/v1/agents/playground/reply", json={"text": text}).json()["bot"]
    invest = bot("Invest")
    assert invest["kind"] == "faq" and "3–5 lakh" in invest["answer"]
    assert bot("abhi busy hoon, 5 baje call karna")["kind"] == "disposition"
    assert bot("Thank you for contacting Royal Graphics, we will get back to you shortly")["kind"] == "auto_reply"
    assert bot("kya ye fraud hai?")["title"].endswith("(trust)")
    assert bot("ok")["kind"] == "step"


# --- Aadhaar from DigiLocker --------------------------------------------------

from src.services import eko_digilocker  # noqa: E402


def test_eko_signature_matches_the_documented_formula():
    import base64, hashlib, hmac
    key = base64.b64encode(b"d2fe1d99-6298-4af2-8cc5-d97dcf46df30").decode()
    want = base64.b64encode(hmac.new(key.encode(), b"1516705204593", hashlib.sha256).digest()).decode()
    assert eko_digilocker.signature("d2fe1d99-6298-4af2-8cc5-d97dcf46df30", "1516705204593") == want
    assert 10 <= len(eko_digilocker.client_ref_id()) <= 20


@pytest.fixture
def digilocker(monkeypatch):
    """Eko's DigiLocker API, stubbed: nothing here reaches it (a fetch is billed)."""
    for k, v in {"EKO_DEVELOPER_KEY": "dev", "EKO_ACCESS_KEY": "acc", "EKO_INITIATOR_ID": "9000000000"}.items():
        monkeypatch.setenv(k, v)
    calls = []
    state = {"ready": True}

    def post(path, body):
        calls.append((path, body))
        if path == eko_digilocker.CREATE_PATH:
            return {"status": 0, "data": {"reference_id": 7483920, "url": "https://digilocker.gov.in/auth?s=1",
                                          "redirect_url": body["redirect_url"]}}
        if not state["ready"]:
            return {"status": 1, "message": "Customer has not completed DigiLocker authorisation yet", "data": {}}
        return {"status": 0, "data": {"verification_status": "SUCCESS", "documents": [{
            "document_type": "AADHAAR", "name": "Vikram Singh", "dob": "12-11-1987", "gender": "M",
            "masked_aadhaar": "XXXX-XXXX-2345", "issue_date": "01-01-2020",
            "address": {"house": "15B", "street": "Nehru Street", "village_or_city": "Chennai",
                        "district": "Chennai", "state": "Tamil Nadu", "pincode": "600001"}}]}}

    monkeypatch.setattr(eko_digilocker, "_post", post)
    return {"calls": calls, "state": state}


def test_the_upload_page_offers_digilocker_only_with_the_keys(db, client, monkeypatch):
    token = _link(db)
    assert '"enabled": false' in client.get(f"/onboard/{token}").text
    assert client.post(f"/onboard/{token}/digilocker").status_code == 503
    for k in ("EKO_DEVELOPER_KEY", "EKO_ACCESS_KEY", "EKO_INITIATOR_ID"):
        monkeypatch.setenv(k, "x")
    assert '"enabled": true' in client.get(f"/onboard/{token}").text


def test_aadhaar_verified_via_digilocker_is_filed_once(db, client, digilocker):
    token = _link(db)
    r = client.post(f"/onboard/{token}/digilocker")
    assert r.json() == {"url": "https://digilocker.gov.in/auth?s=1"}
    path, body = digilocker["calls"][0]
    assert body["redirect_url"] == f"https://link.example.in/onboard/{token}/digilocker/done"
    assert body["document_requested"] == ["AADHAAR"]

    # DigiLocker comes back with the session's verification_id (seen 30 Oct 2026).
    r = client.get(f"/onboard/{token}/digilocker/done?verification_id=3580740241", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"../../{token}?digilocker=verified"
    path, body = digilocker["calls"][1]
    # Eko refuses a list here: "document_type should be AADHAAR/PAN/DRIVING_LICENSE".
    assert body["document_type"] == "AADHAAR" and body["verification_id"] == "3580740241"
    assert body["reference_id"] == "7483920"
    doc = db.query(OnboardingDocument).filter_by(phone=PHONE, doc_type="aadhaar_digilocker").one()
    assert doc.content_type == "application/pdf" and doc.original_name.startswith("Aadhaar (verified")
    assert open(doc.stored_path, "rb").read().startswith(b"%PDF-")
    db.refresh(conv(db))
    kept = conv(db).bot_data["digilocker"]["verified"]
    assert kept["masked_aadhaar"] == "XXXX-XXXX-2345" and kept["pincode"] == "600001"
    assert "photo" not in kept
    assert '"verified": true' in client.get(f"/onboard/{token}").text

    # A reload does not fetch (and pay) again.
    fetches = len(digilocker["calls"])
    client.get(f"/onboard/{token}/digilocker/done", follow_redirects=False)
    assert len(digilocker["calls"]) == fetches

    # It is a verification, not the upload: the Aadhaar copy is still asked for.
    for d in onboarding_bot.REQUIRED_DOCUMENTS:
        if d["key"] != "aadhaar":
            client.post(f"/onboard/{token}/files", data={"doc_type": d["key"]}, files={"file": ("a.pdf", PDF)})
    assert client.post(f"/onboard/{token}/submit").status_code == 400
    client.post(f"/onboard/{token}/files", data={"doc_type": "aadhaar"}, files={"file": ("aadhaar.pdf", PDF)})
    assert client.post(f"/onboard/{token}/submit").json() == {"status": "submitted"}
    db.refresh(conv(db))
    assert conv(db).bot_data["digilocker"]["verified"]
    assert db.query(OnboardingDocument).filter_by(phone=PHONE).count() == 4


def test_digilocker_not_finished_files_nothing_and_can_be_retried(db, client, digilocker):
    token = _link(db)
    digilocker["state"]["ready"] = False
    client.post(f"/onboard/{token}/digilocker")
    r = client.get(f"/onboard/{token}/digilocker/done", follow_redirects=False)
    assert r.headers["location"].endswith("?digilocker=pending")
    assert db.query(OnboardingDocument).filter_by(phone=PHONE, doc_type="aadhaar_digilocker").count() == 0
    digilocker["state"]["ready"] = True
    r = client.get(f"/onboard/{token}/digilocker/done", follow_redirects=False)
    assert r.headers["location"].endswith("?digilocker=verified")
