"""
Composes the template's header image: an AI photograph plus everything else.

Image models cannot be trusted with Indic scripts — the Punjabi posters already
sent carry a Hindi heading and several misspellings — so the photograph is
generated without any text at all, and every word, the Eko logo and the SBI
signboard are set here in HTML with real fonts, then captured by Chromium,
which shapes conjuncts and vowel signs correctly for every script.

The layout follows the posters the team has been sending: logo top-left,
two-line headline with one highlighted phrase, callout box, six benefits,
apply button, and the navy contact footer.
"""
import base64
import html
import os
import re
from typing import List

from src.services import creative_brief

WIDTH, HEIGHT = 1536, 1024
# Meta refuses an image header above 5 MB.
MAX_BYTES = 5 * 1024 * 1024

_ASSETS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")


class PosterError(Exception):
    """The poster could not be rendered; the message says why."""


def _logo_svg() -> str:
    with open(os.path.join(_ASSETS, "eko-logo.svg"), encoding="utf-8") as fh:
        svg = fh.read()
    return svg[svg.index("<svg"):]


def _esc(text) -> str:
    return html.escape(str(text or ""))


def _highlight(text: str, phrase: str, cls: str) -> str:
    """Escapes text and wraps the first occurrence of phrase in a span."""
    safe = _esc(text)
    if phrase and phrase in text:
        safe = safe.replace(_esc(phrase), f'<span class="{cls}">{_esc(phrase)}</span>', 1)
    return safe


def _brand_marks(text: str) -> str:
    """Colours the brand names the way the existing posters do."""
    safe = _esc(text)
    safe = re.sub(r"\bEko\b", '<span class="eko">Eko</span>', safe)
    return re.sub(r"\bSBI\b", '<span class="sbi">SBI</span>', safe)


SBI_MARK = (
    '<svg viewBox="0 0 40 40" width="44" height="44" aria-hidden="true">'
    '<circle cx="20" cy="20" r="19" fill="#29A8E0"/>'
    '<circle cx="20" cy="20" r="5.2" fill="#fff"/>'
    '<rect x="18.2" y="20" width="3.6" height="20" fill="#fff"/></svg>'
)


def build_html(poster: dict, language_code: str, photo: bytes, photo_mime: str) -> str:
    font = creative_brief.LANGUAGES[language_code]["font"]
    font_q = font.replace(" ", "+")
    photo_uri = f"data:{photo_mime};base64,{base64.b64encode(photo).decode()}"

    benefits = "".join(
        f'<div class="cell"><span class="ms">{creative_brief.BENEFIT_ICONS.get(b.get("icon"), "check_circle")}</span>'
        f'<div class="fit t" data-min="12">{_esc(b.get("text"))}</div></div>'
        for b in (poster.get("benefits") or [])[:6]
    )

    return f"""<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans:wght@400;600;700;800&family={font_q}:wght@400;600;700;800&display=block" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,500,1,0&display=block" rel="stylesheet">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:{WIDTH}px;height:{HEIGHT}px;overflow:hidden;background:#fff}}
body{{font-family:"{font}","Noto Sans",sans-serif;color:#14234B;position:relative}}
.ms{{font-family:"Material Symbols Outlined";font-weight:500;font-style:normal;line-height:1;
  font-feature-settings:"liga";-webkit-font-smoothing:antialiased;display:inline-block}}
.abs{{position:absolute}}
.photo{{left:560px;top:0;width:976px;height:904px;background:url('{photo_uri}') center/cover no-repeat}}
.fade{{left:560px;top:0;width:420px;height:904px;background:linear-gradient(90deg,#fff 0%,rgba(255,255,255,.85) 35%,rgba(255,255,255,0) 100%)}}
.logo{{left:48px;top:30px;height:84px}} .logo svg{{height:84px;width:auto}}
.headline{{left:48px;top:128px;width:700px;height:168px;font-size:62px;font-weight:800;line-height:1.2}}
.hl{{color:#F5A300}}
.rule{{left:50px;top:306px;width:560px;height:3px;background:linear-gradient(90deg,#F5A300,#14234B 40%,rgba(20,35,75,0))}}
.sub{{left:48px;top:322px;width:640px;height:112px;font-size:27px;font-weight:600;line-height:1.3}}
.eko{{color:#F5A300;font-weight:800}} .sbi{{color:#1D4ED8;font-weight:800}}
.callout{{left:48px;top:446px;width:650px;height:106px;background:#14234B;color:#fff;border-radius:16px;
  padding:14px 24px;font-size:26px;font-weight:700;line-height:1.3;display:flex;align-items:center}}
.callout .hl{{color:#FFC21A}}
.bx{{left:48px;top:590px;width:860px;height:168px;background:#fff;border:2px solid #C7D2E4;border-radius:14px;
  display:flex;padding:26px 8px 10px}}
.pill{{left:230px;top:570px;height:42px;padding:0 30px;background:#14234B;color:#fff;border-radius:21px;
  font-size:22px;font-weight:700;display:flex;align-items:center;gap:10px;white-space:nowrap}}
.pill:before,.pill:after{{content:"";width:8px;height:8px;border-radius:4px;background:#F5A300}}
.cell{{flex:1;display:flex;flex-direction:column;align-items:center;gap:8px;padding:0 8px;border-right:1px solid #D5DCE8}}
.cell:last-child{{border-right:0}}
.cell .ms{{font-size:46px;color:#14234B}}
.cell .t{{font-size:18px;font-weight:700;line-height:1.25;text-align:center;height:72px;width:100%}}
.cta{{left:48px;top:784px;height:74px;padding:0 34px;background:#14234B;color:#fff;border-radius:18px;
  font-size:32px;font-weight:800;display:flex;align-items:center;gap:18px;white-space:nowrap}}
.cta .ms{{color:#FFC21A;font-size:40px}}
.opp{{left:940px;top:600px;width:560px;height:180px;background:#fff;border:3px solid #F5B400;border-radius:18px;
  display:flex;align-items:center;gap:18px;padding:16px 20px;box-shadow:0 8px 24px rgba(0,0,0,.18)}}
.opp .ic{{flex:none;width:86px;height:86px;border-radius:43px;background:#14234B;display:flex;align-items:center;justify-content:center}}
.opp .ic .ms{{color:#fff;font-size:52px}}
.opp .tx{{flex:1;height:148px;display:flex;flex-direction:column;justify-content:center}}
.opp .tt{{font-size:28px;font-weight:800;line-height:1.2;max-height:70px}}
.opp .ot{{font-size:19px;font-weight:600;line-height:1.3;color:#1F2F5C;margin-top:6px;max-height:76px}}
.sign{{right:34px;top:30px;width:620px;border-radius:12px;overflow:hidden;box-shadow:0 10px 26px rgba(0,0,0,.28)}}
.sign .top{{background:linear-gradient(180deg,#F4F8FD,#DCE8F6);padding:12px 24px 10px}}
.sign .st{{font-size:36px;font-weight:800;color:#14234B;line-height:1.2;height:46px}}
.sign .en{{font-family:"Noto Sans",sans-serif;font-size:30px;font-weight:700;color:#14234B;line-height:1.2}}
.sign .band{{background:#1E3A8A;padding:10px 24px;display:flex;align-items:center;gap:14px;color:#fff}}
.sign .sbiw{{font-family:"Noto Sans",sans-serif;font-size:44px;font-weight:800;letter-spacing:1px}}
.sign .bn{{margin-left:auto;text-align:right;line-height:1.2}}
.sign .bl{{font-size:22px;font-weight:700;height:28px;width:300px}}
.sign .be{{font-family:"Noto Sans",sans-serif;font-size:17px;font-weight:600;letter-spacing:.5px}}
.foot{{left:0;top:904px;width:{WIDTH}px;height:120px;background:#13214A;display:flex;align-items:center;justify-content:center;gap:56px}}
.fc{{display:flex;align-items:center;gap:18px}}
.fi{{width:78px;height:78px;border-radius:39px;background:#F5B400;display:flex;align-items:center;justify-content:center}}
.fi .ms{{font-size:46px;color:#13214A}}
.fg .ms{{font-size:70px;color:#F5B400}}
.fl{{color:#fff;font-size:21px;font-weight:600;height:30px;width:380px}}
.fv{{font-family:"Noto Sans",sans-serif;color:#FFC21A;font-size:42px;font-weight:800;line-height:1.1}}
.div{{width:2px;height:78px;background:rgba(255,255,255,.35)}}
</style></head><body>
<div class="abs photo"></div><div class="abs fade"></div>
<div class="abs logo">{_logo_svg()}</div>
<div class="abs headline fit" id="headline" data-min="40">{_esc(poster.get("headline_line1"))}<br>{_highlight(poster.get("headline_line2", ""), poster.get("headline_highlight"), "hl")}</div>
<div class="abs rule"></div>
<div class="abs sub fit" id="subline" data-min="18">{_brand_marks(poster.get("subline"))}</div>
<div class="abs callout"><div class="fit" id="callout" data-min="18" style="width:100%;max-height:78px">{_highlight(poster.get("callout", ""), poster.get("callout_highlight"), "hl")}</div></div>
<div class="abs bx">{benefits}</div>
<div class="abs pill">{_esc(poster.get("benefits_title"))}</div>
<div class="abs cta">{_esc(poster.get("cta"))}<span class="ms">arrow_forward</span></div>
<div class="abs opp"><div class="ic"><span class="ms">groups</span></div><div class="tx">
  <div class="tt fit" id="opportunity_title" data-min="18">{_esc(poster.get("opportunity_title"))}</div>
  <div class="ot fit" id="opportunity_text" data-min="14">{_esc(poster.get("opportunity_text"))}</div></div></div>
<div class="abs sign"><div class="top"><div class="st fit" id="sign_title" data-min="22">{_esc(poster.get("sign_title"))}</div>
  <div class="en">Customer Service Point</div></div>
  <div class="band">{SBI_MARK}<span class="sbiw">SBI</span><div class="bn">
  <div class="bl fit" id="bank_name" data-min="14">{_esc(poster.get("bank_name"))}</div><div class="be">STATE BANK OF INDIA</div></div></div></div>
<div class="abs foot">
  <div class="fc"><div class="fi"><span class="ms">call</span></div><div>
    <div class="fl fit" id="phone_label" data-min="14">{_esc(poster.get("phone_label"))}</div>
    <div class="fv">{_esc(creative_brief.PHONE)}</div></div></div>
  <div class="div"></div>
  <div class="fc fg"><span class="ms">language</span><div>
    <div class="fl fit" id="web_label" data-min="14">{_esc(poster.get("web_label"))}</div>
    <div class="fv">{_esc(creative_brief.SIGNUP_URL)}</div></div></div>
</div>
</body></html>"""


# Shrinks each .fit element's type until its text fits its box, and reports the
# ones that still do not at their minimum size.
_FIT_JS = """() => {
  const over = el => el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1;
  const bad = [];
  for (const el of document.querySelectorAll('.fit')) {
    let size = parseFloat(getComputedStyle(el).fontSize);
    const min = parseFloat(el.dataset.min || '12');
    while (over(el) && size > min) { size -= 1; el.style.fontSize = size + 'px'; }
    if (over(el)) bad.push(el.id || el.textContent.slice(0, 30));
  }
  return bad;
}"""

_FONTS_JS = """async (families) => {
  await document.fonts.ready;
  const loaded = new Set([...document.fonts].filter(f => f.status === 'loaded')
                          .map(f => f.family.replace(/["']/g, '')));
  return families.filter(f => !loaded.has(f));
}"""


def render(poster: dict, language_code: str, photo: bytes, photo_mime: str) -> bytes:
    """
    Renders the poster to JPEG bytes.

    Refuses rather than guessing when a font did not load — a fallback font
    would quietly draw boxes instead of the state's script — or when text is
    too long for its box even at the smallest allowed size.
    """
    from playwright.sync_api import sync_playwright

    page_html = build_html(poster, language_code, photo, photo_mime)
    needed = [creative_brief.LANGUAGES[language_code]["font"], "Material Symbols Outlined"]

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1)
            page.set_content(page_html, wait_until="networkidle", timeout=60000)
            missing = page.evaluate(_FONTS_JS, needed)
            if missing:
                raise PosterError(f"Fonts did not load: {', '.join(missing)}. The server needs internet access to Google Fonts.")
            overflowing: List[str] = page.evaluate(_FIT_JS)
            if overflowing:
                raise PosterError(f"Text is too long for the poster: {', '.join(overflowing)}")
            image = page.screenshot(type="jpeg", quality=90, full_page=False)
        finally:
            browser.close()

    if len(image) > MAX_BYTES:
        raise PosterError(f"Poster is {len(image) / 1024 / 1024:.1f} MB; WhatsApp allows 5 MB")
    return image
