"""
Only numbers that can actually be dialled in India survive normalisation.

Everything here is a shape that was really in the table. A quarter of the
rows had no contact of any kind, and 605 carried a toll-free helpline that
belonged to the bank whose branch was listed rather than to the business —
the same handful of numbers repeating across hundreds of listings.
"""
import pytest

from src.services.normalizer import is_mobile, normalize_phone


@pytest.mark.parametrize("raw,expected", [
    ("+91 98765 43210", "+919876543210"),
    ("09876543210", "+919876543210"),
    ("9876543210", "+919876543210"),
    ("+919876543210", "+919876543210"),
    ("Phone: 98765 43210", "+919876543210"),
    ("91 98765 43210", "+919876543210"),
])
def test_a_mobile_is_normalised_however_it_was_written(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    # STD codes beginning with 1 are ordinary. A rule barring a leading 1
    # would have dropped the landlines of the districts being scraped.
    ("0181-2234567", "+911812234567"),   # Jalandhar
    ("0183 2456789", "+911832456789"),   # Amritsar
    ("0172-2345678", "+911722345678"),   # Chandigarh
    ("011-23456789", "+911123456789"),   # Delhi
])
def test_a_landline_keeps_its_std_code(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", [
    "18001800",          # eight-digit stub
    "18605005555",       # toll-free, eleven digits
    "18001021021",
    "1800 102 1021",
    "+91 1800 200 3333",
])
def test_a_toll_free_helpline_is_not_a_contact(raw):
    """
    These belong to the bank, not the branch. 18605005555 alone appeared on
    listings in three different states.
    """
    assert normalize_phone(raw) is None


@pytest.mark.parametrize("raw", [
    "+92 300 1234567",   # Pakistan, reached by a Gurdaspur radius
    "+1 415 555 0199",
    "+880 171 1234567",
])
def test_a_foreign_number_is_dropped(raw):
    assert normalize_phone(raw) is None


@pytest.mark.parametrize("raw", [
    "1234", "", None, "abc", "+", "00", "987654321",          # nine digits
    "+91 98765 4321012345",                                   # run together
])
def test_anything_undiallable_becomes_none(raw):
    assert normalize_phone(raw) is None


def test_a_number_starting_with_zero_is_refused():
    """Ten digits is not enough on its own; nothing Indian begins with 0."""
    assert normalize_phone("0123456789") is None


@pytest.mark.parametrize("phone,mobile", [
    ("+919876543210", True),
    ("+916000000000", True),
    ("+911812234567", False),   # landline: no WhatsApp, no SMS
    ("+911123456789", False),
    (None, False),
    ("", False),
])
def test_is_mobile_separates_reachable_from_landline(phone, mobile):
    assert is_mobile(phone) is mobile


def test_the_output_shape_is_always_the_same():
    """
    Campaign recipients are matched to businesses by phone, so one shape
    matters more than which shape.
    """
    for raw in ("9876543210", "09876543210", "+91 9876543210", "91-9876543210"):
        out = normalize_phone(raw)
        assert out == "+919876543210"
        assert len(out) == 13
