"""
Deploy-time migration aligned with auth_service/models.py.
Runs create_all for new tables, then adds any missing columns on existing DBs.
"""
from sqlalchemy import text

from database import engine
import models  # noqa: F401 — registers metadata


def _column_exists(conn, table: str, column: str) -> bool:
    q = text(
        """
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = :table AND column_name = :column
        """
    )
    return conn.execute(q, {"table": table, "column": column}).scalar() > 0


def _table_exists(conn, table: str) -> bool:
    q = text(
        """
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = :table
        """
    )
    return conn.execute(q, {"table": table}).scalar() > 0


def _add_column(conn, table: str, column: str, ddl: str) -> None:
    if not _column_exists(conn, table, column):
        conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {ddl}'))
        print(f"Added {table}.{column}")


# Matches User model — only additive alters for legacy databases
USER_COLUMNS = [
    ("google_id", "VARCHAR"),
    ("hashed_password", "VARCHAR"),
    ("display_name", "VARCHAR"),
    ("avatar", "VARCHAR"),
    ("bio", "VARCHAR"),
    ("specialization", "VARCHAR"),
    ("role", "VARCHAR NOT NULL DEFAULT 'viewer'"),
    ("is_active", "BOOLEAN NOT NULL DEFAULT TRUE"),
    ("is_deleted", "BOOLEAN NOT NULL DEFAULT FALSE"),
    ("created_at", "TIMESTAMPTZ DEFAULT NOW()"),
    ("updated_at", "TIMESTAMPTZ"),
]

# Matches Invite model
INVITE_COLUMNS = [
    ("email", "VARCHAR NOT NULL DEFAULT ''"),
    ("token", "VARCHAR NOT NULL DEFAULT ''"),
    ("role", "VARCHAR NOT NULL DEFAULT 'viewer'"),
    ("is_used", "BOOLEAN NOT NULL DEFAULT FALSE"),
    ("expires_at", "TIMESTAMPTZ"),
    ("created_at", "TIMESTAMPTZ DEFAULT NOW()"),
]


def migrate() -> None:
    print("auth_service: metadata.create_all ...")
    models.Base.metadata.create_all(bind=engine)

    with engine.begin() as conn:
        if not _table_exists(conn, "users"):
            print("auth_service: no users table after create_all; check DATABASE_URL")
        else:
            for col, ddl in USER_COLUMNS:
                _add_column(conn, "users", col, ddl)

        if _table_exists(conn, "invites"):
            for col, ddl in INVITE_COLUMNS:
                _add_column(conn, "invites", col, ddl)

    print("auth_service migrate_deploy: done.")


if __name__ == "__main__":
    migrate()
