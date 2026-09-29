"""
Catching a looked-up point that landed in the wrong place.

These are the real failures that prompted the check: loading a spreadsheet of
Gujarat PIN codes, a bare six-digit search put 385002 in the Caucasus and
three Kheda codes in Lucknow. Each row looked healthy — correct district,
correct state, coordinates a thousand kilometres away — so nothing downstream
would have questioned it.
"""
import pytest

from src.services import geo_bounds


def test_the_caucasus_result_is_caught():
    problem = geo_bounds.check("Gujarat", 44.5999678, 40.0848572)

    assert problem is not None
    assert "outside India" in problem


@pytest.mark.parametrize("pin_district,lat,lon", [
    ("382440 Ahmedabad", 26.86976, 80.9926656),
    ("387004 Kheda", 26.86976, 80.9926656),
    ("387005 Kheda", 26.8757219, 80.9992192),
])
def test_a_lucknow_result_for_a_gujarat_code_is_caught(pin_district, lat, lon):
    problem = geo_bounds.check("Gujarat", lat, lon)

    assert problem is not None
    assert "not in Gujarat" in problem


@pytest.mark.parametrize("state,lat,lon", [
    ("Gujarat", 23.0882825, 72.6978931),      # Ahmedabad
    ("Gujarat", 22.7082393, 72.8574558),      # Kheda
    ("Punjab", 30.9010, 75.8573),             # Ludhiana
    ("Haryana", 28.4595, 77.0266),            # Gurugram
    ("Uttar Pradesh", 26.8467, 80.9462),      # Lucknow, correctly
    ("Maharashtra", 19.0760, 72.8777),        # Mumbai
])
def test_a_point_in_its_own_state_passes(state, lat, lon):
    assert geo_bounds.check(state, lat, lon) is None


def test_case_and_padding_do_not_matter():
    assert geo_bounds.check("  gujarat  ", 23.0225, 72.5714) is None


def test_an_unlisted_state_still_catches_a_result_abroad():
    """
    A state with no rectangle falls back to the country, so the worst case —
    a match on another continent — is still refused.
    """
    assert geo_bounds.check("Nagaland", 25.6747, 94.1086) is None
    assert geo_bounds.check("Nagaland", 48.8566, 2.3522) is not None


def test_missing_coordinates_are_not_this_check_s_problem():
    assert geo_bounds.check("Gujarat", None, None) is None
    assert geo_bounds.check("Gujarat", 23.0, None) is None


def test_the_message_says_what_to_do_about_it():
    problem = geo_bounds.check("Gujarat", 26.86976, 80.9926656)

    assert "anchor name" in problem or "coordinates directly" in problem
