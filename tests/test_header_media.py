"""
A campaign's header media: Meta's id is kept and reused, because the server
uploads to Meta slowly (278 s for 2.1 MB on 30 Oct 2026).
"""
import json
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base
from src.models.app_setting import AppSetting
from src.services import whatsapp_service as ws

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(bind=engine)


def test_a_header_is_uploaded_once_and_reused_while_fresh(tmp_path):
    Base.metadata.create_all(bind=engine, tables=[AppSetting.__table__])
    db = Session()
    path = tmp_path / "header.mp4"
    path.write_bytes(b"0" * 100)

    assert ws._kept_header(db, str(path))[1] is None
    ws._keep_header(db, str(path), "meta-1")
    assert ws._kept_header(db, str(path))[1] == "meta-1"

    # Too old for Meta's 30 days: uploaded afresh.
    row = db.query(AppSetting).filter_by(key=ws.HEADER_MEDIA_KEY + "header.mp4").one()
    kept = json.loads(row.value)
    kept["uploaded_at"] = (datetime.now(timezone.utc) - timedelta(days=ws.HEADER_MEDIA_DAYS + 1)).isoformat()
    row.value = json.dumps(kept)
    db.commit()
    assert ws._kept_header(db, str(path))[1] is None

    # A changed file is uploaded afresh too; keeping it again replaces the row.
    ws._keep_header(db, str(path), "meta-2")
    path.write_bytes(b"1" * 200)
    os.utime(path, (1, 1))
    assert ws._kept_header(db, str(path))[1] is None
    assert db.query(AppSetting).filter_by(key=ws.HEADER_MEDIA_KEY + "header.mp4").count() == 1
    db.close()
