

def test_tara_is_read_from_a_copy_leaving_its_folder_untouched(tmp_path):
    # Run from root's cron, opening Tara's live database could leave a
    # root-owned app.db-shm in Sumit's folder; a private copy is read instead.
    import os
    import sqlite3
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts"))
    import export_business_context as ex

    src = tmp_path / "tara"
    src.mkdir()
    live = sqlite3.connect(src / "app.db")
    live.execute("pragma journal_mode=wal")
    live.execute("pragma wal_autocheckpoint=0")
    live.execute("create table t(x)")
    live.execute("insert into t values (1), (2), (3)")
    live.commit()
    before = sorted(os.listdir(src))
    work = tmp_path / "work"
    work.mkdir()
    copy = ex.snapshot(str(src / "app.db"), str(work))
    assert copy.execute("select count(*) from t").fetchone()[0] == 3   # rows still in the WAL too
    copy.close()
    assert sorted(os.listdir(src)) == before
    live.close()
