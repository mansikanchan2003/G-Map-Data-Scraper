"""
The inbox and the onboarding bot.

Inbound messages of every kind are recorded once, however often Meta
redelivers them. The bot walks someone from an "Interested" tap to uploaded
documents, says nothing it was not asked for, and stays quiet when paused.
The upload page accepts only real PDFs and images, and only on a live link.
"""
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
    AppSetting, Location, OnboardingDocument, WhatsAppButtonClick, WhatsAppCampaign, WhatsAppTemplate,
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

    def send_link_message(self, to, body, text, url):
        StubMeta.sent.append(("link", to, body, {"text": text, "url": url}))
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


@pytest.fixture
def db():
    session = TestingSessionLocal()
    session.add(Location(location_id=uuid.uuid4().hex[:12], pincode=SERVED_PIN,
                         latitude=28.6328, longitude=77.2197, district="New Delhi", state="Delhi"))
    # The bot answers only people a campaign reached, so the test number
    # was sent one; the test that it ignores others uses another number.
    campaign_id = uuid.uuid4().hex
    session.add(WhatsAppCampaign(campaign_id=campaign_id, name="Delhi CSP", data_source_type="scraped",
                                 status="COMPLETED", total_contacts=1))
    session.add(WhatsAppCampaignRecipient(recipient_id=uuid.uuid4().hex, campaign_id=campaign_id,
                                          phone=PHONE, status="READ", provider_message_id="wamid.campaign.base"))
    session.commit()
    try:
        yield session
    finally:
        session.rollback()
        for model in (OnboardingDocument, WhatsAppMessage, WhatsAppConversation, WhatsAppReply,
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
    assert (kind, body) == ("buttons", onboarding_bot.ASK_INVEST)
    assert [b["id"] for b in buttons] == ["invest:yes", "invest:no"]

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
    assert StubMeta.sent[-1][2] == onboarding_bot.ASK_INVEST
    assert conv(db).bot_data["coverage"]["nearest_pincode"] == SERVED_PIN


def test_a_pin_further_away_is_told_we_are_not_there_yet(db, monkeypatch):
    monkeypatch.setattr(pincode_coverage, "_locate_or_none", lambda pin: (19.07, 72.87))  # Mumbai
    tap_campaign(db)
    say(db, "400001")
    assert "not available near 400001" in StubMeta.sent[-1][2]
    assert conv(db).bot_step == onboarding_bot.NOT_SERVED


def test_no_pin_three_times_hands_over_to_a_person(db):
    tap_campaign(db)
    say(db, "hello")
    assert StubMeta.sent[-1][2] == onboarding_bot.BAD_PIN
    say(db, "999")
    say(db, "what?")
    assert StubMeta.sent[-1][2] == onboarding_bot.HANDOVER_TEXT
    assert conv(db).bot_step == onboarding_bot.HANDOVER


def test_saying_no_to_investing_ends_politely(db):
    tap_campaign(db)
    say(db, SERVED_PIN)
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
    say(db, "Haan")
    assert "Aadhaar Card" in StubMeta.sent[-1][2]


def test_another_button_is_acknowledged_without_starting_the_flow(db):
    tap_campaign(db, "Not interested")
    assert [m[2] for m in StubMeta.sent] == [onboarding_bot.ACKNOWLEDGE]
    assert conv(db).bot_step is None


def test_a_pin_sent_out_of_the_blue_is_checked(db):
    say(db, SERVED_PIN)
    assert StubMeta.sent[-1][2] == onboarding_bot.ASK_INVEST


def test_someone_writing_first_is_greeted_and_can_start(db):
    say(db, "Hi, what is this about?")
    kind, _to, body, buttons = StubMeta.sent[-1]
    assert "Thank you for contacting Eko" in body
    assert [b["id"] for b in buttons] == [onboarding_bot.START_INTERESTED, onboarding_bot.START_WEBINAR]
    say(db, "hello?")  # greeted once a day, not on every line
    assert len(StubMeta.sent) == 1
    tap(db, "start:interested")
    tap(db, "lang:en")
    assert StubMeta.sent[-1][2] == onboarding_bot.ASK_PIN


def test_after_not_served_a_new_pin_is_checked_again(db, monkeypatch):
    places = {"400001": (19.07, 72.87), "110017": (28.55, 77.25)}
    monkeypatch.setattr(pincode_coverage, "_locate_or_none", lambda pin: places.get(pin))
    tap_campaign(db)
    say(db, "400001")
    assert conv(db).bot_step == onboarding_bot.NOT_SERVED
    say(db, "ok")
    assert StubMeta.sent[-1][2] == onboarding_bot.NOT_SERVED_AGAIN.format(pin="400001")
    say(db, "try 110017")
    assert StubMeta.sent[-1][2] == onboarding_bot.ASK_INVEST
    assert conv(db).bot_step == onboarding_bot.AWAIT_INVEST


def test_an_unclear_answer_gets_the_question_again(db):
    tap_campaign(db)
    say(db, SERVED_PIN)
    say(db, "what does it involve?")
    kind, _to, body, buttons = StubMeta.sent[-1]
    assert body == onboarding_bot.REMIND_INVEST and [b["id"] for b in buttons] == ["invest:yes", "invest:no"]


def test_an_amount_mid_question_is_not_read_as_a_pin(db):
    tap_campaign(db)
    say(db, SERVED_PIN)
    say(db, "haan, 500000 hai mere paas")
    assert conv(db).bot_step == onboarding_bot.AWAIT_INVEST


def test_replies_stop_after_a_few_it_did_not_understand(db, monkeypatch):
    # An auto-reply answering the bot's answer must not go on for ever.
    monkeypatch.setattr(onboarding_bot, "FALLBACK_GAP", timedelta(0))
    monkeypatch.setattr(onboarding_bot, "GREETING_GAP", timedelta(0))
    for i in range(6):
        say(db, f"Thank you for contacting us! ({i})")
    assert len(StubMeta.sent) == onboarding_bot.MAX_FALLBACK_STREAK


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
    StubMeta.media["d1"] = (b"<html><script>alert(1)</script></html>", "text/html")
    msg = inbox.record_inbound(db, {"from": PHONE.lstrip("+"), "id": "wamid.d1", "type": "document",
                                    "document": {"id": "d1", "filename": "page.html", "mime_type": "text/html"}},
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


def test_webinar_yes(db, told):
    tap_campaign(db, text=campaign_buttons.WEBINAR["en"], lang="hi")
    kind, _to, body, buttons = StubMeta.sent[-1]
    assert body == bot_messages.MESSAGES["hi"]["webinar_ask"]
    assert [b["id"] for b in buttons] == ["webinar:yes", "webinar:no"]
    tap(db, "webinar:yes")
    assert StubMeta.sent[-1][2] == bot_messages.MESSAGES["hi"]["webinar_yes"]
    assert "7291988625" in StubMeta.sent[-1][2]
    assert conv(db).bot_step == onboarding_bot.WEBINAR_CONFIRMED
    assert told and told[0]["phone"] == PHONE


def test_webinar_no_asks_when_and_records_it(db, told):
    tap_campaign(db, text=campaign_buttons.WEBINAR["en"], lang="en")
    tap(db, "webinar:no")
    assert StubMeta.sent[-1][2] == onboarding_bot.WEBINAR_NO
    say(db, "Saturday after 4 pm")
    assert StubMeta.sent[-1][2] == onboarding_bot.WEBINAR_NOTED
    c = conv(db)
    assert c.bot_step == onboarding_bot.WEBINAR_AVAILABILITY
    assert c.bot_data["webinar"]["availability"] == "Saturday after 4 pm"
    assert told[-1]["availability"] == "Saturday after 4 pm"


def test_the_webinar_button_in_a_regional_language_is_recognised(db):
    _punjabi_campaign(db)
    tap_campaign(db, text=campaign_buttons.WEBINAR["pa"], lang="pa")
    assert StubMeta.sent[-1][2] == bot_messages.MESSAGES["pa"]["webinar_ask"]


def test_the_language_is_remembered_for_the_next_flow(db, told):
    tap_campaign(db, text=campaign_buttons.WEBINAR["en"], lang="hi")
    tap(db, "webinar:yes")
    count = len(StubMeta.sent)
    tap_campaign(db, lang=None)  # Interested, after the webinar
    assert len(StubMeta.sent) == count + 1
    assert StubMeta.sent[-1][2] == bot_messages.MESSAGES["hi"]["ask_pin"]


def test_every_language_has_every_message_and_short_buttons():
    keys = set(bot_messages.MESSAGES["en"])
    for lang, msgs in bot_messages.MESSAGES.items():
        assert set(msgs) == keys, lang
        for k in ("yes", "no", "link_button"):
            assert len(msgs[k]) <= 20, (lang, k)
    for label in campaign_buttons.WEBINAR.values():
        assert len(label) <= 20 and campaign_buttons.is_webinar(label)
    assert not campaign_buttons.is_webinar("Interested")
