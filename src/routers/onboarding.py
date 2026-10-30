"""
The document upload page the onboarding bot links to.

Public, because the person opening it has no account: the unguessable token
in the link is what identifies them, and it lapses after a week. It lives
outside /api/ for the same reason the campaign redirect does, so the session
gate never sees it.

Each file is checked by its first bytes, not its name or the type the browser
claims, and is stored outside anything served statically. Only signed-in
users read them back, through the inbox.
"""
import json
import logging
import os
import re
import uuid
from datetime import timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from src.database import get_db
from src.models.inbox import OnboardingDocument, WhatsAppConversation
from src.models.whatsapp import WhatsAppAccount
from src.services import auth_service, drive_uploads, eko_digilocker, inbox, notifier, onboarding_bot

logger = logging.getLogger("gmap_scraper.onboarding")

router = APIRouter(tags=["Onboarding Upload"])

DOCS_DIR = os.environ.get("ONBOARDING_DOCS_DIR", os.path.join("data", "onboarding_documents"))
MAX_BYTES = 5 * 1024 * 1024
ACCEPTED_LABEL = "PDF, JPG or PNG, up to 5 MB"
IST = timezone(timedelta(hours=5, minutes=30))

_ASSETS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")

# What a file really is, from its first bytes.
_SIGNATURES = (
    (b"%PDF-", "application/pdf", "pdf"),
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
)


def sniff(head: bytes):
    for magic, content_type, ext in _SIGNATURES:
        if head.startswith(magic):
            return content_type, ext
    return None


def business_number() -> str:
    """Our WhatsApp number in digits, for the wa.me link back into the chat."""
    configured = re.sub(r"\D", "", os.environ.get("WHATSAPP_BUSINESS_NUMBER", ""))
    if configured:
        return configured
    from src.database import SessionLocal
    db = SessionLocal()
    try:
        accounts = db.query(WhatsAppAccount).all()
        pid = os.environ.get("META_PHONE_NUMBER_ID")
        ordered = ([a for a in accounts if pid and a.phone_number_id == pid]
                   + [a for a in accounts if a.status == "Connected"])
        for a in ordered:
            digits = re.sub(r"\D", "", a.phone_number or "")
            if len(digits) >= 10:
                return digits
    finally:
        db.close()
    return ""


def _conversation(db: Session, token: str):
    """The conversation a live, unexpired token belongs to, or None."""
    if not token or len(token) > 64:
        return None
    conv = db.query(WhatsAppConversation).filter(WhatsAppConversation.upload_token == token).first()
    if conv is None:
        return None
    expires = inbox.aware(conv.upload_token_expires_at)
    if not expires or expires <= inbox.now():
        return None
    return conv


@router.get("/onboard/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(os.path.join(_ASSETS, "eko-favicon.ico"), media_type="image/x-icon")


@router.get("/onboard/{token}", response_class=HTMLResponse, include_in_schema=False)
def upload_page(token: str, db: Session = Depends(get_db)):
    conv = _conversation(db, token)
    uploaded = {}
    if conv:
        for d in db.query(OnboardingDocument).filter(OnboardingDocument.phone == conv.phone).all():
            uploaded[d.doc_type] = d.original_name or "Uploaded"

    number = business_number()
    config = {
        "state": "invalid" if conv is None else ("submitted" if conv.documents_submitted_at else "open"),
        "documents": onboarding_bot.DOCUMENTS,
        "uploaded": uploaded,
        "accepted": ACCEPTED_LABEL,
        "maxBytes": MAX_BYTES,
        "whatsapp": f"https://wa.me/{number}" if number else None,
        # Aadhaar, PAN and the licence can come from DigiLocker in place of an upload.
        "digilocker": {
            "enabled": eko_digilocker.configured(),
            "rows": {d["row"]: d["label"] for d in onboarding_bot.DIGILOCKER_DOCS},
            "got": sorted(_got(conv)) if conv else [],
        },
    }
    with open(os.path.join(_ASSETS, "eko-logo.svg"), encoding="utf-8") as fh:
        logo = fh.read()
    logo = logo[logo.index("<svg"):]

    html = (PAGE
            .replace("__LOGO__", logo)
            # "</" closes the script tag the JSON sits in, whatever follows it.
            .replace("__CONFIG__", json.dumps(config).replace("</", "<\\/")))
    return HTMLResponse(html, headers={
        "Cache-Control": "no-store",
        "X-Robots-Tag": "noindex",
        "Referrer-Policy": "no-referrer",
    })


@router.post("/onboard/{token}/files", include_in_schema=False)
async def upload_file(
    token: str,
    doc_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    conv = _conversation(db, token)
    if conv is None:
        raise HTTPException(status_code=404, detail="This link has expired. Please ask us for a new one on WhatsApp.")
    if conv.documents_submitted_at:
        raise HTTPException(status_code=409, detail="Your documents have already been submitted.")
    if doc_type not in {d["key"] for d in onboarding_bot.DOCUMENTS}:
        raise HTTPException(status_code=400, detail="Unknown document")

    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="This file is larger than 5 MB. Please upload a smaller one.")
    if not data:
        raise HTTPException(status_code=400, detail="This file is empty.")
    kind = sniff(data[:16])
    if kind is None:
        raise HTTPException(status_code=415, detail="Please upload a PDF, JPG or PNG file.")
    content_type, ext = kind

    name = os.path.basename(file.filename or "")[:255] or f"{doc_type}.{ext}"
    _store(db, conv, doc_type, data, name, content_type, ext)
    db.commit()
    logger.info(f"onboarding event=FILE_UPLOADED phone=...{conv.phone[-4:]} doc={doc_type} bytes={len(data)}")
    return {"doc_type": doc_type, "name": name}


def _store(db: Session, conv, doc_type: str, data: bytes, name: str, content_type: str, ext: str) -> None:
    """Keep a document's file, replacing the last one of its kind. The caller commits."""
    folder = os.path.join(DOCS_DIR, re.sub(r"\D", "", conv.phone))
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{doc_type}-{uuid.uuid4().hex}.{ext}")
    with open(path, "wb") as fh:
        fh.write(data)

    # One file per document: a new upload replaces the last.
    for old in db.query(OnboardingDocument).filter(
        OnboardingDocument.phone == conv.phone, OnboardingDocument.doc_type == doc_type
    ).all():
        try:
            os.remove(old.stored_path)
        except OSError:
            pass
        db.delete(old)

    db.add(OnboardingDocument(
        document_id=uuid.uuid4().hex, phone=conv.phone, doc_type=doc_type,
        original_name=name, stored_path=path, content_type=content_type, size_bytes=len(data),
    ))


# --- Documents from DigiLocker (see services/eko_digilocker) -----------------

# Each document DigiLocker gives is filed as its own record and fills its row,
# so the person uploads only the rest.
DIGILOCKER_BY_EKO = {d["eko"]: d for d in onboarding_bot.DIGILOCKER_DOCS}


def _digilocker(conv) -> dict:
    return dict((conv.bot_data or {}).get("digilocker") or {})


def _set_digilocker(conv, **fields) -> None:
    conv.bot_data = {**(conv.bot_data or {}), "digilocker": {**_digilocker(conv), **fields}}


def _got(conv) -> set:
    """The rows filled from DigiLocker: fetched, or (before 30 Oct 2026) the Aadhaar verified."""
    dl = _digilocker(conv)
    rows = set((dl.get("got") or {}).keys())
    if dl.get("verified"):
        rows.add("aadhaar")
    return rows


@router.post("/onboard/{token}/digilocker", include_in_schema=False)
def digilocker_start(token: str, db: Session = Depends(get_db)):
    """A one-time DigiLocker link for this person, asking for what it has not given yet."""
    conv = _conversation(db, token)
    if conv is None:
        raise HTTPException(status_code=404, detail="This link has expired. Please ask us for a new one on WhatsApp.")
    if conv.documents_submitted_at:
        raise HTTPException(status_code=409, detail="Your documents have already been submitted.")
    if not eko_digilocker.configured():
        raise HTTPException(status_code=503, detail="DigiLocker is not available just now. Please upload your documents instead.")
    got = _got(conv)
    types = [d["eko"] for d in onboarding_bot.DIGILOCKER_DOCS if d["row"] not in got]
    if not types:
        raise HTTPException(status_code=409, detail="Your documents from DigiLocker are already here.")
    back = f"{onboarding_bot.public_base_url()}/onboard/{token}/digilocker/done"
    try:
        session = eko_digilocker.create_url(back, types)
    except eko_digilocker.DigiLockerError as e:
        raise HTTPException(status_code=502, detail=str(e))
    _set_digilocker(conv, reference_id=session["reference_id"],
                    verification_id=session.get("verification_id"),
                    started_at=inbox.now().isoformat(), asked=types, tried=[])
    db.commit()
    logger.info(f"onboarding event=DIGILOCKER_STARTED phone=...{conv.phone[-4:]} asked={','.join(types)}")
    return {"url": session["url"]}


@router.get("/onboard/{token}/digilocker/done", include_in_schema=False)
def digilocker_done(token: str, request: Request, db: Session = Depends(get_db)):
    """
    Where DigiLocker sends the person back. Each document asked for is
    fetched once and filed in its row, and they go back to the upload page,
    which says what came.
    """
    page = f"../../{token}"
    conv = _conversation(db, token)
    if conv is None:
        return RedirectResponse(page, status_code=303)
    dl = _digilocker(conv)
    if not dl.get("reference_id"):
        return RedirectResponse(page, status_code=303)

    # DigiLocker names the session's verification id on the way back.
    verification_id = (request.query_params.get("verification_id") or request.query_params.get("verificationId")
                       or dl.get("verification_id"))
    logger.info(f"onboarding event=DIGILOCKER_BACK phone=...{conv.phone[-4:]} params={sorted(request.query_params.keys())}")
    got = _got(conv)
    # A reload does not fetch (and pay for) a document again; one not given yet is asked once more, free if refused.
    todo = [t for t in (dl.get("asked") or [eko_digilocker.DOCUMENT_TYPE])
            if t in DIGILOCKER_BY_EKO and DIGILOCKER_BY_EKO[t]["row"] not in got]
    fetched, failed = [], False
    verified_at = inbox.now().astimezone(IST).strftime("%d %b %Y, %I:%M %p IST")
    for kind in todo:
        spec = DIGILOCKER_BY_EKO[kind]
        try:
            doc = eko_digilocker.fetch(kind, dl["reference_id"], verification_id)
        except eko_digilocker.DigiLockerError:
            failed = True
            continue
        if doc is None:
            continue
        doc = {**doc, "document_type": kind}
        title = eko_digilocker.TITLES.get(kind, kind.title())
        _store(db, conv, spec["key"], eko_digilocker.pdf(doc, verified_at), f"{title} (from DigiLocker).pdf",
               "application/pdf", "pdf")
        entry = {**eko_digilocker.summary(doc), "at": inbox.now().isoformat()}
        _set_digilocker(conv, got={**(_digilocker(conv).get("got") or {}), spec["row"]: entry})
        if kind == eko_digilocker.DOCUMENT_TYPE:
            _set_digilocker(conv, verified=eko_digilocker.summary(doc), verified_at=entry["at"])
        db.commit()
        fetched.append(spec["row"])
    _set_digilocker(conv, tried=todo)
    db.commit()
    logger.info(f"onboarding event=DIGILOCKER_FETCHED phone=...{conv.phone[-4:]} "
                f"asked={','.join(todo) or '-'} got={','.join(fetched) or '-'}")
    if fetched:
        outcome = "fetched"
    elif failed:
        outcome = "failed"
    elif got:
        outcome = "fetched"
    else:
        outcome = "pending"
    return RedirectResponse(f"{page}?digilocker={outcome}", status_code=303)


@router.post("/onboard/{token}/submit", include_in_schema=False)
def submit(token: str, background: BackgroundTasks, db: Session = Depends(get_db)):
    conv = _conversation(db, token)
    if conv is None:
        raise HTTPException(status_code=404, detail="This link has expired. Please ask us for a new one on WhatsApp.")
    if conv.documents_submitted_at:
        return {"status": "submitted"}

    # A document from DigiLocker fills its row as an upload does.
    have = onboarding_bot.rows_done(
        d.doc_type for d in db.query(OnboardingDocument).filter(OnboardingDocument.phone == conv.phone).all())
    # Only the required documents hold up a submission; the rest are sent
    # if the person has them.
    missing = [d["label"] for d in onboarding_bot.REQUIRED_DOCUMENTS if d["key"] not in have]
    if missing:
        raise HTTPException(status_code=400, detail="Please upload: " + ", ".join(missing))

    msg = onboarding_bot.documents_submitted(db, conv)
    db.commit()
    if msg.status == "FAILED":
        # The documents are in either way; the inbox shows the failed thank-you.
        logger.warning(f"onboarding event=THANKS_NOT_SENT phone=...{conv.phone[-4:]} reason={msg.error_reason}")

    background.add_task(drive_uploads.save_in_background, conv.phone)
    background.add_task(notifier.notify_documents_submitted, auth_service.BOOTSTRAP_ADMIN, {
        "name": conv.profile_name, "phone": conv.phone,
        "pincode": ((conv.bot_data or {}).get("coverage") or {}).get("pincode"),
        "documents": [d["label"] for d in onboarding_bot.DOCUMENTS if d["key"] in have],
    })
    return {"status": "submitted"}


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Eko · Upload documents</title>
<link rel="icon" type="image/x-icon" href="favicon.ico">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@600;700;800&display=swap" rel="stylesheet">
<style>
  :root {
    --gold: #f9ab10; --gold-hover: #e09706; --teal: #094053; --navy: #0c2531;
    --page: #eef5f6; --card: #ffffff; --ink: #0c2531; --muted: #557080;
    --line: #d5e3e7; --ok: #0f8a5f; --ok-bg: #e6f6ef; --err: #c0392b; --err-bg: #fdecea;
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--page); color: var(--ink);
         font: 16px/1.5 Inter, system-ui, sans-serif; -webkit-font-smoothing: antialiased; }
  header { background: var(--navy); padding: 18px 16px 64px; text-align: center; }
  header svg { height: 44px; width: auto; }
  main { max-width: 560px; margin: -48px auto 32px; padding: 0 16px; }
  .card { background: var(--card); border-radius: 16px; box-shadow: 0 6px 24px rgba(12,37,49,.10);
          padding: 22px 18px; }
  h1 { font: 700 1.35rem/1.25 "Plus Jakarta Sans", Inter, sans-serif; margin: 0 0 6px; }
  .lead { color: var(--muted); margin: 0 0 18px; font-size: .95rem; }
  .accepted { display: inline-block; background: #fff6e0; color: #7a5300; border: 1px solid #f6d58a;
              border-radius: 999px; font-size: .78rem; font-weight: 600; padding: 3px 10px; margin-bottom: 16px; }
  .doc { display: flex; align-items: center; gap: 12px; padding: 14px 0; border-top: 1px solid var(--line); }
  .doc:first-of-type { border-top: 0; }
  .doc .info { flex: 1; min-width: 0; }
  .doc .name { font-weight: 600; }
  .doc .hint, .doc .file { font-size: .82rem; color: var(--muted); overflow-wrap: anywhere; }
  .tag { display: inline-block; font-size: .7rem; font-weight: 700; border-radius: 999px; padding: 1px 8px; margin-top: 3px; }
  .tag.req { background: #fdecea; color: #a93226; }
  .tag.opt { background: var(--page); color: var(--muted); }
  .doc .file.ok { color: var(--ok); font-weight: 600; }
  .doc .file.err { color: var(--err); font-weight: 600; }
  .num { flex: none; width: 28px; height: 28px; border-radius: 50%; background: var(--page);
         color: var(--teal); font-weight: 700; font-size: .85rem; display: grid; place-items: center; }
  .doc.done .num { background: var(--ok-bg); color: var(--ok); }
  .pick { flex: none; position: relative; }
  .pick input { position: absolute; inset: 0; opacity: 0; cursor: pointer; width: 100%; }
  .btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; border: 0;
         border-radius: 10px; font: 600 .9rem Inter, sans-serif; padding: 10px 14px; cursor: pointer;
         text-decoration: none; min-height: 44px; }
  .btn-outline { background: #fff; color: var(--teal); border: 1.5px solid var(--teal); }
  .doc.done .btn-outline { color: var(--muted); border-color: var(--line); }
  .btn-primary { background: var(--gold); color: var(--navy); width: 100%; font-size: 1rem; margin-top: 18px; }
  .btn-primary:hover { background: var(--gold-hover); }
  .btn-primary:disabled { background: #e7eef0; color: #94a9b3; cursor: not-allowed; }
  .btn-wa { background: #25d366; color: #fff; width: 100%; margin-top: 16px; font-size: 1rem; }
  .pick input:focus-visible + .btn, .btn:focus-visible { outline: 3px solid var(--gold); outline-offset: 2px; }
  .banner { border-radius: 10px; padding: 10px 12px; font-size: .9rem; margin-top: 14px; display: none; }
  .banner.err { display: block; background: var(--err-bg); color: var(--err); }
  .banner.ok { display: block; background: var(--ok-bg); color: var(--ok); font-weight: 600; }
  .banner.top { margin: 0 0 14px; }
  .dl { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin: 0 0 16px; padding: 14px;
        border-radius: 14px; background: linear-gradient(135deg, #eaf3ff, #f2ecff); border: 1px solid #d6e2fb; }
  .dl .icon { font-size: 1.6rem; line-height: 1; }
  .dl .why { flex: 1; min-width: 180px; font-size: .84rem; color: #3b4f8a; }
  .dl .why b { display: block; font-size: .95rem; color: #1d2f6f; margin-bottom: 2px; }
  .dl .chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
  .dl .chip { font-size: .72rem; font-weight: 700; border-radius: 999px; padding: 2px 9px; background: #fff; color: #3b4f8a;
              border: 1px solid #d6e2fb; }
  .dl .chip.got { background: var(--ok-bg); color: var(--ok); border-color: #bfe6d3; }
  .dl[hidden] { display: none; }
  .tag.dlg { background: var(--ok-bg); color: var(--ok); }
  .btn-dl { background: #3b5bdb; color: #fff; min-height: 44px; padding: 8px 14px; font-size: .9rem; }
  .btn-dl:hover { background: #2f4bc0; }
  .btn-dl:disabled { background: #a5b4e8; cursor: wait; }
  .verified { display: inline-flex; align-items: center; gap: 4px; background: var(--ok-bg); color: var(--ok);
              font-size: .72rem; font-weight: 700; border-radius: 999px; padding: 2px 9px; margin-left: 6px; }
  .center { text-align: center; }
  .big { font-size: 3rem; line-height: 1; margin: 6px 0 10px; }
  footer { text-align: center; color: var(--muted); font-size: .78rem; margin: 18px 0 0; }
  .spin { width: 16px; height: 16px; border: 2px solid currentColor; border-right-color: transparent;
          border-radius: 50%; animation: s .7s linear infinite; }
  @keyframes s { to { transform: rotate(360deg); } }
</style>
</head>
<body>
<header>__LOGO__</header>
<main><div class="card" id="app"></div>
<footer>Your documents are shared securely with Eko and used only for your onboarding.</footer></main>
<script>
const CFG = __CONFIG__;
const app = document.getElementById('app');
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const base = location.pathname.replace(/\\/+$/, '');
const backButton = () => CFG.whatsapp
  ? `<a class="btn btn-wa" href="${esc(CFG.whatsapp)}">Back to WhatsApp</a>` : '';

function done(title, text) {
  app.innerHTML = `<div class="center"><div class="big">✅</div><h1>${title}</h1>
    <p class="lead">${text}</p>${backButton()}</div>`;
}

if (CFG.state === 'invalid') {
  app.innerHTML = `<div class="center"><div class="big">⌛</div><h1>This link has expired</h1>
    <p class="lead">Please reply on WhatsApp and we'll send you a new one.</p>${backButton()}</div>`;
} else if (CFG.state === 'submitted') {
  done('Documents received', 'Thank you for sharing your documents. One of our team members will reach out to you shortly.');
} else {
  const uploaded = Object.assign({}, CFG.uploaded);
  const DL = Object.assign({ enabled: false, rows: {}, got: [] }, CFG.digilocker);
  const got = new Set(DL.got);
  // A row is done by an upload, or by the same document from DigiLocker.
  const filled = key => !!uploaded[key] || got.has(key);
  app.innerHTML = `<h1>Upload your documents</h1>
    <p class="lead">The first three are required. Please add the others too if you have them, then tap Submit.</p>
    <div class="banner top" id="dlmsg" role="status"></div>
    <div class="dl" id="dlcard" hidden></div>
    <span class="accepted">Accepted formats: ${esc(CFG.accepted)}</span>
    <div id="docs"></div>
    <div class="banner" id="msg" role="alert"></div>
    <button class="btn btn-primary" id="submit" disabled>Submit documents</button>`;

  const docs = document.getElementById('docs');
  CFG.documents.forEach((d, i) => {
    const row = document.createElement('div');
    row.className = 'doc';
    row.innerHTML = `<div class="num">${i + 1}</div>
      <div class="info"><div class="name">${esc(d.label)}</div>
        <span class="tag ${d.required ? 'req' : 'opt'}">${d.required ? 'Required' : 'Optional'}</span>
        <div class="hint">${d.hint ? esc(d.hint) : ''}</div><div class="file" aria-live="polite"></div></div>
      <label class="pick"><input type="file" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
        aria-label="Upload ${esc(d.label)}"><span class="btn btn-outline">Upload</span></label>`;
    docs.appendChild(row);
    const input = row.querySelector('input'), btn = row.querySelector('.pick .btn'), file = row.querySelector('.file');
    const tag = row.querySelector('.tag');
    const show = () => {
      const name = uploaded[d.key], fromDl = got.has(d.key);
      row.classList.toggle('done', filled(d.key));
      file.className = 'file' + (name ? ' ok' : '');
      file.textContent = name ? '✓ ' + name : '';
      if (fromDl) {
        // DigiLocker has given it: the upload becomes optional.
        tag.className = 'tag dlg';
        tag.textContent = '✓ From DigiLocker';
      }
      btn.textContent = name ? 'Replace' : (fromDl ? 'Add copy' : 'Upload');
      refresh();
    };
    input.addEventListener('change', async () => {
      const f = input.files[0];
      input.value = '';
      if (!f) return;
      if (f.size > CFG.maxBytes) { file.className = 'file err'; file.textContent = 'This file is larger than 5 MB.'; return; }
      btn.innerHTML = '<span class="spin"></span>';
      input.disabled = true;
      const body = new FormData();
      body.append('doc_type', d.key);
      body.append('file', f);
      try {
        const res = await fetch(base + '/files', { method: 'POST', body });
        const out = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(out.detail || 'Upload failed. Please try again.');
        uploaded[d.key] = out.name;
        show();
      } catch (e) {
        show();
        file.className = 'file err';
        file.textContent = e.message || 'Upload failed. Please try again.';
      } finally {
        input.disabled = false;
      }
    });
    show();
  });

  // Documents from DigiLocker: off to DigiLocker's own sign-in, and back here.
  function dlCard() {
    const card = document.getElementById('dlcard');
    const rows = Object.keys(DL.rows);
    const left = rows.filter(r => !got.has(r));
    if (!DL.enabled || !left.length) { card.hidden = true; return; }
    const name = r => (CFG.documents.find(d => d.key === r) || {}).label || r;
    const short = { aadhaar: 'Aadhaar', pan: 'PAN', voter_dl: 'Driving Licence' };
    card.hidden = false;
    card.innerHTML = `<div class="icon">📲</div>
      <div class="why"><b>${got.size ? 'Get the rest from DigiLocker' : 'Get your documents from DigiLocker'}</b>
        Sign in on DigiLocker and share them: we fetch them for you, so you upload only what is missing.
        <div class="chips">${rows.map(r => `<span class="chip ${got.has(r) ? 'got' : ''}" title="${esc(name(r))}">${got.has(r) ? '✓ ' : ''}${esc(short[r] || name(r))}</span>`).join('')}</div>
      </div>
      <button type="button" class="btn btn-dl">🔐 ${got.size ? 'Try again' : 'Fetch from DigiLocker'}</button>`;
    const b = card.querySelector('button');
    b.addEventListener('click', async () => {
      const msg = document.getElementById('dlmsg');
      b.disabled = true;
      b.innerHTML = '<span class="spin"></span> Opening…';
      try {
        const res = await fetch(base + '/digilocker', { method: 'POST' });
        const out = await res.json().catch(() => ({}));
        if (!res.ok || !out.url) throw new Error(out.detail || 'DigiLocker could not be opened. Please try again.');
        location.href = out.url;
      } catch (e) {
        msg.className = 'banner top err';
        msg.textContent = e.message;
        b.disabled = false;
        b.textContent = '🔐 Fetch from DigiLocker';
      }
    });
  }
  dlCard();

  const back = new URLSearchParams(location.search).get('digilocker');
  if (back) {
    const msg = document.getElementById('dlmsg');
    const short = { aadhaar: 'Aadhaar', pan: 'PAN', voter_dl: 'Driving Licence' };
    const names = [...got].map(r => short[r] || r).join(', ');
    // Only a required document DigiLocker did not give is called out; the licence is optional.
    const required = new Set(CFG.documents.filter(d => d.required).map(d => d.key));
    const missing = Object.keys(DL.rows).filter(r => !got.has(r) && required.has(r)).map(r => short[r] || r).join(', ');
    const says = {
      fetched: ['ok', `✅ From DigiLocker: ${names}.` + (missing
        ? ` ${missing} did not come from DigiLocker, so please upload ${missing.includes(',') ? 'them' : 'it'} with the rest below.`
        : ' Now upload the remaining documents below.')],
      verified: ['ok', `✅ From DigiLocker: ${names}. Now upload the remaining documents.`],
      pending: ['err', 'Nothing came from DigiLocker. Please finish sharing there and try again, or upload your documents below.'],
      failed: ['err', 'We could not reach DigiLocker just now. Please try again in a minute, or upload your documents below.'],
    }[back];
    if (says) { msg.className = 'banner top ' + says[0]; msg.textContent = says[1]; }
    history.replaceState(null, '', location.pathname);
  }

  function refresh() {
    const left = CFG.documents.filter(d => d.required && !filled(d.key)).length;
    const b = document.getElementById('submit');
    if (!b) return;
    b.disabled = left > 0;
    b.textContent = left ? `Submit documents (${left} required left)` : 'Submit documents';
  }
  refresh();

  document.getElementById('submit').addEventListener('click', async e => {
    const b = e.currentTarget, msg = document.getElementById('msg');
    b.disabled = true;
    b.innerHTML = '<span class="spin"></span> Submitting…';
    msg.className = 'banner';
    try {
      const res = await fetch(base + '/submit', { method: 'POST' });
      const out = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(out.detail || 'Could not submit. Please try again.');
      done('Thank you!', 'Your documents have been submitted. Taking you back to WhatsApp…');
      if (CFG.whatsapp) setTimeout(() => { location.href = CFG.whatsapp; }, 1800);
    } catch (err) {
      msg.className = 'banner err';
      msg.textContent = err.message;
      refresh();
    }
  });
}
</script>
</body>
</html>
"""
