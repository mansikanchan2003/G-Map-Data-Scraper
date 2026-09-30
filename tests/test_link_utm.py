"""
Tagging the campaign destination so analytics can attribute the visit.

The trap this guards against: everything after "#" stays in the browser and
never reaches the destination's server, so a utm written into the fragment is
invisible to analytics — and appending anything after an anchor breaks the
anchor too.
"""
import pytest

from src.routers.tracking import _with_campaign_source


def test_the_anchor_survives_and_the_utm_lands_in_the_query():
    out = _with_campaign_source("https://kiosk.eko.in/#apply-now", "Punjab Campaign5")

    # The jump still works...
    assert out.endswith("#apply-now")
    # ...and the tags are where a server can actually read them.
    query = out.split("#")[0]
    assert "utm_source=AutoGMap" in query
    assert "utm_medium=whatsapp" in query
    assert "utm_campaign=Punjab+Campaign5" in query


def test_nothing_is_appended_after_the_fragment():
    """
    The shape that does not work: .../#apply-now/autogmap/r/{{1}} makes the
    whole tail part of the fragment, so the anchor no longer matches and the
    tracker is never reached.
    """
    out = _with_campaign_source("https://kiosk.eko.in/#apply-now", "X")

    assert out.count("#") == 1
    assert out.split("#")[1] == "apply-now"


def test_an_existing_query_is_kept():
    out = _with_campaign_source("https://kiosk.eko.in/?ref=partner#apply-now", "X")

    assert "ref=partner" in out
    assert "utm_source=" in out
    assert out.endswith("#apply-now")


def test_a_source_already_set_is_not_overwritten():
    """A target that names its own source means it deliberately."""
    out = _with_campaign_source("https://kiosk.eko.in/?utm_source=Billboard", "X")

    assert "utm_source=Billboard" in out
    assert "utm_source=AutoGMap" not in out


def test_a_campaign_without_a_name_gets_no_empty_tag():
    out = _with_campaign_source("https://kiosk.eko.in/", "")

    assert "utm_campaign=" not in out
    assert "utm_source=" in out


@pytest.mark.parametrize("url", [
    "https://kiosk.eko.in/",
    "https://kiosk.eko.in/apply",
    "https://kiosk.eko.in/apply?a=1&b=2#anchor",
])
def test_the_host_and_path_are_never_altered(url):
    out = _with_campaign_source(url, "Camp")

    assert out.startswith(url.split("?")[0].split("#")[0])


def test_an_unknown_token_still_reaches_the_apply_page_with_its_source():
    """
    A token that no longer resolves — a deleted recipient, an old link, or
    the template's own "{{1}}" opened by hand — used to land on a bare home
    page: no anchor, no source. Only the campaign name is genuinely unknown.
    """
    out = _with_campaign_source("https://kiosk.eko.in/signup?utm_source=AutoGMap")

    assert out.startswith("https://kiosk.eko.in/signup?")
    assert "utm_source=AutoGMap" in out
    assert "utm_campaign=" not in out


def test_the_default_destination_is_the_signup_page_with_the_autogmap_source(monkeypatch):
    """
    Signups from these links must be recorded by the kiosk site as AutoGMap.

    /signup rather than /#apply-now: the home page grows after loading, so the
    jump to #apply-now stopped short of the form on both desktop and phone.
    """
    import importlib
    import src.routers.tracking as tracking
    from src.services.whatsapp_service import tracking_link_for

    monkeypatch.delenv("CAMPAIGN_LINK_TARGET_URL", raising=False)
    monkeypatch.delenv("CAMPAIGN_LINK_FALLBACK_URL", raising=False)
    monkeypatch.delenv("CAMPAIGN_UTM_SOURCE", raising=False)
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    importlib.reload(tracking)

    assert tracking_link_for("abc") == "https://kiosk.eko.in/signup?utm_source=AutoGMap"
    out = tracking._with_campaign_source(tracking.FALLBACK_URL, "Punjab Campaign5")
    assert out.startswith("https://kiosk.eko.in/signup?utm_source=AutoGMap&")
    assert "utm_campaign=Punjab+Campaign5" in out
    # A bare destination gets AutoGMap as its source too.
    assert "utm_source=AutoGMap" in tracking._with_campaign_source("https://kiosk.eko.in/signup", "X")
