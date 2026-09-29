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
    assert "utm_source=WhatsApp+Campaign" in query
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
    assert "utm_source=WhatsApp" not in out


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
