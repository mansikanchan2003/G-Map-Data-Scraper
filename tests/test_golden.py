"""The golden evaluation set (src/evals/golden.py) runs with the tests, so a change that breaks it fails here."""
import json

from src.evals import golden


def test_every_golden_case_passes():
    report = golden.run()
    failed = [f"{f['id']}: {f['title']} -> {'; '.join(f['problems'])}" for f in report["failures"]]
    assert not failed, "\n".join(failed)
    assert report["total"] >= 80


def test_the_set_covers_every_suite_and_each_case_is_well_formed():
    cases = golden.load_cases()
    assert {c["suite"] for c in cases} == set(golden.CHECKERS)
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids))
    for c in cases:
        assert c["title"] and c["expect"]


def test_a_broken_expectation_is_reported_not_raised(monkeypatch):
    bad = {"id": "x", "suite": "faq", "title": "made up", "text": "hello", "expect": {"faq": ["fees"]}}
    monkeypatch.setattr(golden, "load_cases", lambda suite=None: [bad])
    report = golden.run()
    assert report["total"] == 1 and report["passed"] == 0 and report["failures"][0]["problems"]


def test_a_disposition_that_drifts_from_the_sheet_is_caught(monkeypatch):
    # The sheet check is only worth something if it fails when the code and the sheet disagree.
    import copy
    rows = [c for c in golden.load_cases("disposition_sheet") if c["row"]["label"] == "Busy"]
    wrong = copy.deepcopy(rows[0])
    wrong["row"]["owner"] = "Human"
    wrong["row"]["email"] = True
    wrong["row"]["after"] = "Closed: nothing more is sent"
    monkeypatch.setattr(golden, "load_cases", lambda suite=None: [wrong])
    report = golden.run()
    problems = " ".join(report["failures"][0]["problems"])
    assert "owner" in problems and "ticket and email" in problems and "closes the lead" in problems

