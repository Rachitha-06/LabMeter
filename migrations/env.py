from logging.config import fileConfig  # noqa: F401  (kept for alembic init compatibility)

from alembic import context

from app.config import DATABASE_URL
from app.db import models  # noqa: F401  (registers every table on Base.metadata)
from app.db.base import Base
from app.db.session import make_engine

config = context.config
url = config.get_main_option("sqlalchemy.url") or DATABASE_URL
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,  # SQLite needs batch mode for ALTER operations
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = make_engine(url)  # same engine settings as the app, including SQLite foreign keys
    with connectable.connect() as connection:
        if connection.dialect.name == "sqlite":
            # SQLite rebuilds a table when a migration changes it. With foreign keys enforced, dropping the
            # old parent table would cascade into child rows and delete them. Turn enforcement off for the
            # migration run only; the application turns it back on for its own connections.
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.commit()  # the pragma opens a transaction; close it before alembic starts its own
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
