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
