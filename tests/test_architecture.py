"""
Phase 2 (22 Nov 2026): every file belongs to a module (src/architecture/modules.py), and no
new code reaches across modules. The baseline lists the reaches that were there when the map
was drawn; it may only shrink.
"""
from src.architecture import boundaries as b


def test_every_file_belongs_to_a_module():
    assert b.unassigned() == [], "Give these files a module in src/architecture/modules.py"


def test_no_new_reach_across_modules():
    fresh = b.new_reaches()
    assert not fresh, (
        "New imports across modules. Use the other module's platform-level service, move the code to the "
        "module that owns it, or (only if truly needed) discuss before adding it to the baseline:\n"
        + "\n".join(f"  {f} -> {t}" for f, t in fresh))


def test_the_baseline_only_lists_reaches_that_still_exist():
    # A reach that was removed must come out of the baseline, so it cannot creep back.
    gone = b.load_baseline() - set(b.reaches())
    assert not gone, "Shrink the baseline: python -m src.architecture.boundaries --update\n" + \
        "\n".join(f"  {f} -> {t}" for f, t in sorted(gone))


def test_the_checker_sees_a_model_imported_through_src_models():
    # "from src.models import WhatsAppConversation" is a reach into conversation's table.
    assert "models/inbox" in b._imports("services/applications")
