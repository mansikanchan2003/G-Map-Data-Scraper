import pytest
from src.services.whatsapp_normalizer import WhatsAppNormalizer

def test_whatsapp_normalizer_valid_formats():
    valid_inputs = [
        ("9911844469", "+919911844469"),
        ("+919911844469", "+919911844469"),
        ("919911844469", "+919911844469"),
        (" 9911844469 ", "+919911844469"),
        ("'9911844469'", "+919911844469"),
        ('"9911844469"', "+919911844469"),
        ("“9911844469”", "+919911844469"),
        (9911844469, "+919911844469"),
        (9911844469.0, "+919911844469"),
        ("'9911844469", "+919911844469"), # Excel style leading quote
    ]

    for raw, expected in valid_inputs:
        canonical, error = WhatsAppNormalizer.normalize_phone(raw)
        assert error is None
        assert canonical == expected

def test_whatsapp_normalizer_invalid_formats():
    invalid_inputs = [
        (None, "Empty phone number"),
        ("", "Empty phone number"),
        ("   ", "Empty phone number"),
        ("9911844469.5", "Invalid formatting or characters"),
        (9911844469.5, "Non-integer phone value"),
        ("99 118 44469", "Invalid formatting or characters"),
        ("0112345678", "Landline or invalid mobile number"),
        ("abc9911844469", "Invalid formatting or characters"),
        ("123", "Invalid length (3 digits)"),
        ("+19911844469", "Invalid length (11 digits)"),
    ]

    for raw, expected_error in invalid_inputs:
        canonical, error = WhatsAppNormalizer.normalize_phone(raw)
        assert canonical is None
        assert expected_error in error


class TestRejectedEditsDoNotDiverge:
    """
    Meta renders a message from its own approved copy, so a local edit it
    refuses changes nothing for recipients — but the send path builds its
    parameters from the local row. A button retyped here while still a Call
    at Meta made every send fail with "#132018 ... does not support
    parameters", which is why a refused edit is rolled back.
    """

    def test_the_route_snapshots_content_before_applying(self):
        import inspect

        from src.routers import whatsapp
        source = inspect.getsource(whatsapp.update_template)
        assert "previous = {k: getattr(db_tmpl, k) for k in CONTENT_FIELDS}" in source

    def test_a_refused_push_restores_the_previous_content(self):
        import inspect

        from src.routers import whatsapp
        source = inspect.getsource(whatsapp.update_template)
        idx = source.index('result["status"] != "success"')
        after = source[idx:idx + 600]
        assert "for key, value in previous.items()" in after
        assert "setattr(db_tmpl, key, value)" in after

    def test_the_message_says_a_new_template_is_needed(self):
        import inspect

        from src.routers import whatsapp
        source = inspect.getsource(whatsapp.update_template)
        # Telling someone the edit "did not apply" without saying what to do
        # instead leaves them retrying the same thing.
        assert "needs a new template" in source
