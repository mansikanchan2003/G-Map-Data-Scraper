"""
More poster layouts, from the team's reference posters, so drafts do not all
share one structure.

Each takes the same poster text as the classic layout (poster_renderer), so the
agent writes and the checks judge one set of fields, whatever the layout:

- list:   benefits as a vertical list with round icons, the opportunity in a
          card with a yellow header strip, the Eko logo on a tab top right.
- banner: the photo across the top with the headline over it; subline,
          callout and benefits in two columns below.
- mirror: the photo on the left and the text on the right, a yellow callout
          box, benefits as a three-by-two grid.

Every word set here comes from the poster; the only fixed text is brand
names, the phone number and the address.
"""
import base64

from src.services import creative_brief
from src.services.poster_renderer import (
    HEIGHT, SBI_MARK, WIDTH, _brand_marks, _esc, _highlight, _logo_svg,
)


def _icon(b: dict) -> str:
    return creative_brief.BENEFIT_ICONS.get(b.get("icon"), "check_circle")


def _head(language_code: str, css: str) -> str:
    font = creative_brief.LANGUAGES[language_code]["font"]
    font_q = font.replace(" ", "+")
    return f"""<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans:wght@400;600;700;800&family={font_q}:wght@400;600;700;800&display=block" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,500,1,0&display=block" rel="stylesheet">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:{WIDTH}px;height:{HEIGHT}px;overflow:hidden;background:#fff}}
body{{font-family:"{font}","Noto Sans",sans-serif;color:#14234B;position:relative}}
.ms{{font-family:"Material Symbols Outlined";font-weight:500;font-style:normal;line-height:1;
  font-feature-settings:"liga";-webkit-font-smoothing:antialiased;display:inline-block}}
.abs{{position:absolute}} .hl{{color:#F5A300}} .eko{{color:#F5A300;font-weight:800}} .sbi{{color:#1D4ED8;font-weight:800}}
.sign{{border-radius:12px;overflow:hidden;box-shadow:0 10px 26px rgba(0,0,0,.28)}}
.sign .top{{background:linear-gradient(180deg,#F4F8FD,#DCE8F6);padding:10px 22px 8px}}
.sign .st{{font-size:32px;font-weight:800;color:#14234B;line-height:1.2;height:40px}}
.sign .en{{font-family:"Noto Sans",sans-serif;font-size:26px;font-weight:700;color:#14234B;line-height:1.2}}
.sign .band{{background:#1E3A8A;padding:8px 22px;display:flex;align-items:center;gap:12px;color:#fff}}
.sign .sbiw{{font-family:"Noto Sans",sans-serif;font-size:40px;font-weight:800;letter-spacing:1px}}
.sign .bn{{margin-left:auto;text-align:right;line-height:1.2}}
.sign .bl{{font-size:20px;font-weight:700;height:26px;width:260px}}
.sign .be{{font-family:"Noto Sans",sans-serif;font-size:15px;font-weight:600;letter-spacing:.5px}}
.foot{{left:0;top:904px;width:{WIDTH}px;height:120px;background:#13214A;display:flex;align-items:center;justify-content:center;gap:56px}}
.fc{{display:flex;align-items:center;gap:18px}}
.fi{{width:78px;height:78px;border-radius:39px;background:#F5B400;display:flex;align-items:center;justify-content:center}}
.fi .ms{{font-size:46px;color:#13214A}} .fg .ms{{font-size:70px;color:#F5B400}}
.fl{{color:#fff;font-size:21px;font-weight:600;height:30px;width:380px}}
.fv{{font-family:"Noto Sans",sans-serif;color:#FFC21A;font-size:42px;font-weight:800;line-height:1.1}}
.div{{width:2px;height:78px;background:rgba(255,255,255,.35)}}
{css}
</style></head><body>"""


def _photo(photo: bytes, photo_mime: str) -> str:
    return f"data:{photo_mime};base64,{base64.b64encode(photo).decode()}"


def _sign(poster: dict, style: str) -> str:
    return f"""<div class="abs sign" style="{style}"><div class="top"><div class="st fit" id="sign_title" data-min="20">{_esc(poster.get("sign_title"))}</div>
  <div class="en">Customer Service Point</div></div>
  <div class="band">{SBI_MARK}<span class="sbiw">SBI</span><div class="bn">
  <div class="bl fit" id="bank_name" data-min="13">{_esc(poster.get("bank_name"))}</div><div class="be">STATE BANK OF INDIA</div></div></div></div>"""


def _footer(poster: dict) -> str:
    return f"""<div class="abs foot">
  <div class="fc"><div class="fi"><span class="ms">call</span></div><div>
    <div class="fl fit" id="phone_label" data-min="14">{_esc(poster.get("phone_label"))}</div>
    <div class="fv">{_esc(creative_brief.PHONE)}</div></div></div>
  <div class="div"></div>
  <div class="fc fg"><span class="ms">language</span><div>
    <div class="fl fit" id="web_label" data-min="14">{_esc(poster.get("web_label"))}</div>
    <div class="fv">{_esc(creative_brief.SIGNUP_URL)}</div></div></div>
</div></body></html>"""


def _headline(poster: dict) -> str:
    return (f'{_esc(poster.get("headline_line1"))}<br>'
            f'{_highlight(poster.get("headline_line2", ""), poster.get("headline_highlight"), "hl")}')


def build_list(poster: dict, language_code: str, photo: bytes, photo_mime: str) -> str:
    """Benefits as a vertical list, the opportunity card with a yellow header."""
    rows = "".join(
        f'<div class="row"><div class="ic"><span class="ms">{_icon(b)}</span></div>'
        f'<div class="fit rt" data-min="16">{_esc(b.get("text"))}</div></div>'
        for b in (poster.get("benefits") or [])[:5]
    )
    css = f"""
.photo{{left:500px;top:0;width:1036px;height:904px;background:url('{_photo(photo, photo_mime)}') center/cover no-repeat}}
.fade{{left:500px;top:0;width:460px;height:904px;background:linear-gradient(90deg,#fff 0%,rgba(255,255,255,.88) 38%,rgba(255,255,255,0) 100%)}}
.logo{{right:0;top:0;padding:26px 40px 22px 44px;background:#fff;border-bottom-left-radius:34px}} .logo svg{{height:78px;width:auto;display:block}}
.headline{{left:56px;top:48px;width:780px;height:230px;font-size:76px;font-weight:800;line-height:1.18}}
.sub{{left:56px;top:290px;width:740px;height:118px;font-size:29px;font-weight:600;line-height:1.32}}
.pill{{left:56px;top:430px;height:56px;padding:0 30px;background:#14234B;color:#fff;border-radius:14px 14px 0 0;
  font-size:26px;font-weight:700;display:flex;align-items:center}}
.box{{left:56px;top:486px;width:520px;height:400px;background:#fff;border:2px solid #C7D2E4;border-radius:0 14px 14px 14px;padding:6px 22px}}
.row{{display:flex;align-items:center;gap:18px;height:77px;border-bottom:1px solid #D5DCE8}} .row:last-child{{border-bottom:0}}
.row .ic{{flex:none;width:56px;height:56px;border-radius:28px;background:#14234B;display:flex;align-items:center;justify-content:center}}
.row .ic .ms{{color:#fff;font-size:32px}} .row .rt{{flex:1;font-size:24px;font-weight:700;height:64px;display:flex;align-items:center}}
.opp{{left:640px;top:660px;width:580px;height:224px;border-radius:18px;overflow:hidden;box-shadow:0 10px 26px rgba(0,0,0,.25)}}
.opp .hd{{background:#F5B400;height:74px;display:flex;align-items:center;gap:16px;padding:0 22px}}
.opp .hd .ms{{font-size:44px;color:#14234B}} .opp .tt{{flex:1;font-size:28px;font-weight:800;height:40px}}
.opp .bd{{background:#14234B;color:#fff;height:150px;padding:16px 24px}} .opp .ot{{font-size:24px;font-weight:600;line-height:1.35;height:118px}}
"""
    return _head(language_code, css) + f"""
<div class="abs photo"></div><div class="abs fade"></div>
<div class="abs logo">{_logo_svg()}</div>
<div class="abs headline fit" id="headline" data-min="44">{_headline(poster)}</div>
<div class="abs sub fit" id="subline" data-min="18">{_brand_marks(poster.get("subline"))}</div>
<div class="abs pill">{_esc(poster.get("benefits_title"))}</div>
<div class="abs box">{rows}</div>
<div class="abs opp"><div class="hd"><span class="ms">groups</span><div class="tt fit" id="opportunity_title" data-min="18">{_esc(poster.get("opportunity_title"))}</div></div>
  <div class="bd"><div class="ot fit" id="opportunity_text" data-min="15">{_esc(poster.get("opportunity_text"))}</div></div></div>
{_sign(poster, "left:1000px;top:190px;width:500px")}
""" + _footer(poster)


def build_banner(poster: dict, language_code: str, photo: bytes, photo_mime: str) -> str:
    """The photo across the top with the headline over it; two columns below."""
    chips = "".join(
        f'<div class="chip"><span class="ms">{_icon(b)}</span><div class="fit ct" data-min="14">{_esc(b.get("text"))}</div></div>'
        for b in (poster.get("benefits") or [])[:6]
    )
    css = f"""
.photo{{left:0;top:0;width:{WIDTH}px;height:540px;background:url('{_photo(photo, photo_mime)}') center 35%/cover no-repeat}}
.shade{{left:0;top:200px;width:{WIDTH}px;height:340px;background:linear-gradient(180deg,rgba(19,33,74,0) 0%,rgba(19,33,74,.82) 70%,rgba(19,33,74,.92) 100%)}}
.logo{{left:0;top:0;padding:22px 40px 20px 40px;background:#fff;border-bottom-right-radius:30px}} .logo svg{{height:70px;width:auto;display:block}}
.headline{{left:48px;top:330px;width:1000px;height:190px;font-size:74px;font-weight:800;line-height:1.18;color:#fff}}
.headline .hl{{color:#FFC21A}}
.sub{{left:48px;top:560px;width:640px;height:100px;font-size:27px;font-weight:600;line-height:1.32}}
.call{{left:48px;top:672px;width:640px;height:110px;background:#FFF3CF;border-left:10px solid #F5B400;border-radius:12px;
  padding:12px 22px;font-size:26px;font-weight:700;line-height:1.3;display:flex;align-items:center}}
.cta{{left:48px;top:800px;height:76px;padding:0 34px;background:#14234B;color:#fff;border-radius:38px;
  font-size:31px;font-weight:800;display:flex;align-items:center;gap:16px;white-space:nowrap}} .cta .ms{{color:#FFC21A;font-size:38px}}
.pill{{left:740px;top:556px;height:44px;padding:0 24px;background:#14234B;color:#fff;border-radius:22px;font-size:22px;font-weight:700;display:flex;align-items:center}}
.grid{{left:740px;top:612px;width:748px;height:270px;display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.chip{{display:flex;align-items:center;gap:14px;background:#F2F6FC;border:2px solid #D3DEEE;border-radius:14px;padding:0 16px;height:82px}}
.chip .ms{{font-size:40px;color:#14234B}} .chip .ct{{flex:1;font-size:22px;font-weight:700;height:60px;display:flex;align-items:center}}
"""
    return _head(language_code, css) + f"""
<div class="abs photo"></div><div class="abs shade"></div>
<div class="abs logo">{_logo_svg()}</div>
{_sign(poster, "right:34px;top:26px;width:520px")}
<div class="abs headline fit" id="headline" data-min="44">{_headline(poster)}</div>
<div class="abs sub fit" id="subline" data-min="18">{_brand_marks(poster.get("subline"))}</div>
<div class="abs call"><div class="fit" id="callout" data-min="17" style="width:100%;max-height:86px">{_highlight(poster.get("callout", ""), poster.get("callout_highlight"), "hl")}</div></div>
<div class="abs cta">{_esc(poster.get("cta"))}<span class="ms">arrow_forward</span></div>
<div class="abs pill">{_esc(poster.get("benefits_title"))}</div>
<div class="abs grid">{chips}</div>
""" + _footer(poster)


def build_mirror(poster: dict, language_code: str, photo: bytes, photo_mime: str) -> str:
    """The photo on the left, the text on the right, a yellow callout box."""
    cells = "".join(
        f'<div class="cell"><span class="ms">{_icon(b)}</span><div class="fit t" data-min="13">{_esc(b.get("text"))}</div></div>'
        for b in (poster.get("benefits") or [])[:6]
    )
    css = f"""
.photo{{left:0;top:0;width:1000px;height:904px;background:url('{_photo(photo, photo_mime)}') center/cover no-repeat}}
.fade{{left:560px;top:0;width:440px;height:904px;background:linear-gradient(270deg,#fff 0%,rgba(255,255,255,.88) 35%,rgba(255,255,255,0) 100%)}}
.logo{{right:48px;top:34px;height:80px}} .logo svg{{height:80px;width:auto}}
.headline{{left:880px;top:136px;width:620px;height:200px;font-size:64px;font-weight:800;line-height:1.18}}
.rule{{left:882px;top:346px;width:420px;height:4px;background:linear-gradient(90deg,#F5A300,#14234B 50%,rgba(20,35,75,0))}}
.sub{{left:880px;top:362px;width:620px;height:96px;font-size:25px;font-weight:600;line-height:1.3}}
.call{{left:880px;top:470px;width:620px;height:96px;background:#F5B400;border-radius:16px;padding:10px 22px;
  font-size:25px;font-weight:800;line-height:1.3;display:flex;align-items:center}}
.call .hl{{background:#14234B;color:#FFC21A;padding:0 8px;border-radius:6px}}
.pill{{left:880px;top:584px;height:40px;padding:0 22px;background:#14234B;color:#fff;border-radius:20px;font-size:20px;font-weight:700;display:flex;align-items:center}}
.grid{{left:880px;top:632px;width:620px;height:176px;display:grid;grid-template-columns:repeat(3,1fr);gap:8px}}
.cell{{display:flex;align-items:center;gap:10px;background:#fff;border:2px solid #C7D2E4;border-radius:12px;padding:0 10px}}
.cell .ms{{font-size:34px;color:#14234B}} .cell .t{{flex:1;font-size:17px;font-weight:700;line-height:1.2;height:72px;display:flex;align-items:center}}
.cta{{left:880px;top:822px;height:66px;padding:0 30px;background:#14234B;color:#fff;border-radius:16px;
  font-size:28px;font-weight:800;display:flex;align-items:center;gap:14px;white-space:nowrap}} .cta .ms{{color:#FFC21A;font-size:34px}}
"""
    return _head(language_code, css) + f"""
<div class="abs photo"></div><div class="abs fade"></div>
{_sign(poster, "left:34px;top:30px;width:500px")}
<div class="abs logo">{_logo_svg()}</div>
<div class="abs headline fit" id="headline" data-min="40">{_headline(poster)}</div>
<div class="abs rule"></div>
<div class="abs sub fit" id="subline" data-min="17">{_brand_marks(poster.get("subline"))}</div>
<div class="abs call"><div class="fit" id="callout" data-min="16" style="width:100%;max-height:76px">{_highlight(poster.get("callout", ""), poster.get("callout_highlight"), "hl")}</div></div>
<div class="abs pill">{_esc(poster.get("benefits_title"))}</div>
<div class="abs grid">{cells}</div>
<div class="abs cta">{_esc(poster.get("cta"))}<span class="ms">arrow_forward</span></div>
""" + _footer(poster)
