"""
A PIN added to the locations sheet without coordinates.

Such rows used to be skipped without a word, so a PIN typed into the sheet
never reached the server. They are now placed from the PIN code, checked
against their state, and anything that still cannot be loaded is reported.
"""
import openpyxl
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.config import settings
from src.database import Base
from src.models import Category, Location
from src.services import config_loader, pincode_coverage

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(bind=engine)
Base.metadata.create_all(bind=engine)

HEADER = ("PIN Code", "Latitude", "Longitude", "District", "State", "Tehsil", "Anchor Village/Town")


@pytest.fixture
def sheets(tmp_path, monkeypatch):
    loc = openpyxl.Workbook()
    ws = loc.active
    ws.append(HEADER)
    ws.append((110001, 28.63, 77.22, "New Delhi", "Delhi", "Chanakyapuri", "Connaught Place"))
    ws.append((160055, None, None, "MOHALI", "Punjab", "SAS Nagar", "SAS Nagar"))
    ws.append((999999, None, None, "Nowhere", "Punjab", None, None))
    ws.append((400001, None, None, "Mumbai", "Punjab", None, None))  # placed in the wrong state
    loc.save(tmp_path / "loc.xlsx")
    cat = openpyxl.Workbook()
    cat.active.append(("Category",))
    cat.active.append(("Kirana store",))
    cat.save(tmp_path / "cat.xlsx")

    monkeypatch.setattr(settings, "locations_file", str(tmp_path / "loc.xlsx"))
    monkeypatch.setattr(settings, "categories_file", str(tmp_path / "cat.xlsx"))
    places = {"160055": (30.7109, 76.7072), "400001": (18.94, 72.83)}
    monkeypatch.setattr(pincode_coverage, "_locate_or_none", lambda pin: places.get(pin))

    db = Session()
    yield db
    db.query(Location).delete()
    db.query(Category).delete()
    db.commit()
    db.close()


def test_a_pin_without_coordinates_is_placed_from_its_code(sheets):
    out = config_loader.sync_config(sheets)

    mohali = sheets.query(Location).filter(Location.pincode == "160055").one()
    assert (mohali.latitude, mohali.longitude) == (30.7109, 76.7072)
    assert mohali.coordinate_precision == "pin_geocoded"
    assert mohali.state == "Punjab"
    assert out["locations"]["new"] == 2


def test_rows_that_cannot_be_placed_are_reported_not_dropped(sheets):
    out = config_loader.sync_config(sheets)

    skipped = {s["pincode"]: s["reason"] for s in out["locations"]["skipped"]}
    assert set(skipped) == {"999999", "400001"}
    assert "could not be found" in skipped["999999"]
    assert "looks wrong" in skipped["400001"]
    assert sheets.query(Location).filter(Location.pincode.in_(["999999", "400001"])).count() == 0
