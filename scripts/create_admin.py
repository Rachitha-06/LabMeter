#!/usr/bin/env python3
"""Create the first administrator account.

Usage:
    python scripts/create_admin.py --email admin@your-college.example

The password is read from the LABMETER_ADMIN_PASSWORD environment variable if set, otherwise prompted
for without echo. It is never written to disk or printed.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.auth.passwords import hash_password  # noqa: E402
from app.config import DATABASE_URL, PASSWORD_MIN_LENGTH  # noqa: E402
from app.db import models as m  # noqa: E402
from app.db.session import make_engine, make_session_factory  # noqa: E402
from app.validation.schemas import normalise_email  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", required=True)
    parser.add_argument("--db-url", default=DATABASE_URL)
    args = parser.parse_args(argv)

    try:
        email = normalise_email(args.email)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1

    password = os.environ.get("LABMETER_ADMIN_PASSWORD") or getpass.getpass("Admin password: ")
    if len(password) < PASSWORD_MIN_LENGTH:
        print(f"password must be at least {PASSWORD_MIN_LENGTH} characters", file=sys.stderr)
        return 1

    Session = make_session_factory(make_engine(args.db_url))
    with Session() as session:
        if session.scalar(select(m.User).where(m.User.email == email)) is not None:
            print("a user with that email already exists", file=sys.stderr)
            return 1
        session.add(m.User(email=email, password_hash=hash_password(password), role="admin", is_active=True))
        session.commit()
    print(f"Created administrator {email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
