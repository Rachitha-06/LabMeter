import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import backup_db  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.session import make_engine  # noqa: E402


def test_sqlite_backup_is_a_complete_copy(tmp_path):
    source = tmp_path / "live.db"
    engine = make_engine(f"sqlite:///{source}")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql("INSERT INTO laboratories (name, building, lab_type, computer_count, timezone) "
                             "VALUES ('Backup Test Lab', 'B', 'T', 5, 'UTC')")
    engine.dispose()

    out = tmp_path / "backups" / "copy.sqlite3"
    assert backup_db.main(["--db-url", f"sqlite:///{source}", "--out", str(out)]) == 0
    names = [row[0] for row in sqlite3.connect(out).execute("SELECT name FROM laboratories")]
    assert names == ["Backup Test Lab"]


def test_backup_never_overwrites_an_existing_file(tmp_path):
    source = tmp_path / "live.db"
    make_engine(f"sqlite:///{source}").dispose()
    out = tmp_path / "copy.sqlite3"
    out.write_bytes(b"precious")
    with pytest.raises(SystemExit):
        backup_db.main(["--db-url", f"sqlite:///{source}", "--out", str(out)])
    assert out.read_bytes() == b"precious"
