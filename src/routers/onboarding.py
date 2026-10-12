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

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session

from src.database import get_db
from src.models.inbox import OnboardingDocument, WhatsAppConversation
from src.models.whatsapp import WhatsAppAccount
from src.services import auth_service, drive_uploads, inbox, notifier, onboarding_bot

logger = logging.getLogger("gmap_scraper.onboarding")

router = APIRouter(tags=["Onboarding Upload"])

DOCS_DIR = os.environ.get("ONBOARDING_DOCS_DIR", os.path.join("data", "onboarding_documents"))
MAX_BYTES = 5 * 1024 * 1024
ACCEPTED_LABEL = "PDF, JPG or PNG, up to 5 MB"

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

    name = os.path.basename(file.filename or "")[:255] or f"{doc_type}.{ext}"
    db.add(OnboardingDocument(
        document_id=uuid.uuid4().hex, phone=conv.phone, doc_type=doc_type,
        original_name=name, stored_path=path, content_type=content_type, size_bytes=len(data),
    ))
    db.commit()
    logger.info(f"onboarding event=FILE_UPLOADED phone=...{conv.phone[-4:]} doc={doc_type} bytes={len(data)}")
    return {"doc_type": doc_type, "name": name}


@router.post("/onboard/{token}/submit", include_in_schema=False)
def submit(token: str, background: BackgroundTasks, db: Session = Depends(get_db)):
    conv = _conversation(db, token)
    if conv is None:
        raise HTTPException(status_code=404, detail="This link has expired. Please ask us for a new one on WhatsApp.")
    if conv.documents_submitted_at:
        return {"status": "submitted"}

    have = {d.doc_type for d in db.query(OnboardingDocument).filter(OnboardingDocument.phone == conv.phone).all()}
    missing = [d["label"] for d in onboarding_bot.DOCUMENTS if d["key"] not in have]
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
        "documents": [d["label"] for d in onboarding_bot.DOCUMENTS],
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
  app.innerHTML = `<h1>Upload your documents</h1>
    <p class="lead">Please upload each document below, then tap Submit.</p>
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
        <div class="hint">${d.hint ? esc(d.hint) : ''}</div><div class="file" aria-live="polite"></div></div>
      <label class="pick"><input type="file" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
        aria-label="Upload ${esc(d.label)}"><span class="btn btn-outline">Upload</span></label>`;
    docs.appendChild(row);
    const input = row.querySelector('input'), btn = row.querySelector('.btn'), file = row.querySelector('.file');
    const show = () => {
      const name = uploaded[d.key];
      row.classList.toggle('done', !!name);
      file.className = 'file' + (name ? ' ok' : '');
      file.textContent = name ? '✓ ' + name : '';
      btn.textContent = name ? 'Replace' : 'Upload';
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

  function refresh() {
    const left = CFG.documents.filter(d => !uploaded[d.key]).length;
    const b = document.getElementById('submit');
    if (!b) return;
    b.disabled = left > 0;
    b.textContent = left ? `Submit documents (${left} left)` : 'Submit documents';
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
