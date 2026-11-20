#!/usr/bin/env python3
"""Back up the LabMeter database to a single file.

SQLite:      uses SQLite's online backup API, so it is safe while the server is running.
PostgreSQL:  runs pg_dump in custom format (needs the PostgreSQL client tools on PATH).

Usage:
    python scripts/backup_db.py --out backups/labmeter-2026-10-18.dump
    python scripts/backup_db.py --db-url sqlite:///./labmeter.db --out backups/labmeter.sqlite3

Restore:
    SQLite:      copy the backup file over the database file while the server is stopped.
    PostgreSQL:  pg_restore --clean --if-exists --no-owner -d "$DATABASE_URL_PLAIN" backups/labmeter.dump
Keep at least one copy off the machine that runs the server.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import DATABASE_URL  # noqa: E402


def sqlite_path(url: str) -> Path:
    prefix = "sqlite:///"
    return Path(unquote(url[len(prefix):]))


def backup_sqlite(url: str, out: Path) -> None:
    source = sqlite3.connect(sqlite_path(url))
    target = sqlite3.connect(out)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()


def backup_postgres(url: str, out: Path) -> None:
    if shutil.which("pg_dump") is None:
        raise SystemExit("pg_dump was not found on PATH. Install the PostgreSQL client tools.")
    plain = url.replace("postgresql+psycopg://", "postgresql://")
    parsed = urlparse(plain)
    env = dict(os.environ)
    if parsed.password:
        env["PGPASSWORD"] = unquote(parsed.password)
    command = ["pg_dump", "--format=custom", "--no-owner", "--file", str(out),
               "--host", parsed.hostname or "localhost", "--port", str(parsed.port or 5432),
               "--username", unquote(parsed.username or ""), parsed.path.lstrip("/")]
    subprocess.run(command, check=True, env=env)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db-url", default=DATABASE_URL)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.out.exists():
        raise SystemExit(f"{args.out} already exists; choose a new file name so an old backup is not overwritten")
    if args.db_url.startswith("sqlite"):
        backup_sqlite(args.db_url, args.out)
    elif args.db_url.startswith("postgresql"):
        backup_postgres(args.db_url, args.out)
    else:
        raise SystemExit("unsupported database URL")
    print(f"Backup written to {args.out} ({args.out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
