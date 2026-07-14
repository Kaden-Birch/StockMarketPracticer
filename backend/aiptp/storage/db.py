import enum
import logging
from decimal import Decimal

from sqlalchemy import String, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator

log = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class DecimalStr(TypeDecorator):
    """Exact decimal storage as TEXT — SQLite has no true NUMERIC type and we
    never want money or share quantities passing through binary floats."""

    impl = String(40)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return str(Decimal(value))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return Decimal(value)


def make_engine(db_url: str) -> Engine:
    engine = create_engine(db_url, connect_args={"check_same_thread": False} if db_url.startswith("sqlite") else {})
    if db_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()
    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def _default_literal(column) -> str | None:
    """SQL literal for a column's Python-side default, when it's a constant
    we can express in DDL. Callable defaults (uuid, utcnow) return None —
    those columns are added nullable and only matter for new rows, which the
    ORM populates."""
    default = getattr(column, "default", None)
    arg = getattr(default, "arg", None)
    if arg is None or callable(arg):
        return None
    if isinstance(arg, bool):
        return "1" if arg else "0"
    if isinstance(arg, (int, float)):
        return str(arg)
    if isinstance(arg, Decimal):
        return f"'{arg}'"
    if isinstance(arg, enum.Enum):
        arg = arg.value
    if isinstance(arg, str):
        escaped = arg.replace("'", "''")
        return f"'{escaped}'"
    return None


def auto_upgrade(engine: Engine) -> list[str]:
    """Pre-1.0 schema upgrader: after create_all has made any brand-new
    tables, add columns that exist on the models but not in an older SQLite
    database, backfilling constant defaults. Additive only — never drops or
    rewrites data — so a `git pull` + restart upgrades old installs in place
    instead of crashing with 'no such column'. Returns the applied DDL."""
    if engine.dialect.name != "sqlite":
        return []
    applied: list[str] = []
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            rows = conn.exec_driver_sql(
                f'PRAGMA table_info("{table.name}")').fetchall()
            existing = {row[1] for row in rows}
            if not existing:
                continue  # brand-new table: create_all already built it fully
            for column in table.columns:
                if column.name in existing:
                    continue
                col_type = column.type.compile(engine.dialect)
                ddl = (f'ALTER TABLE "{table.name}" '
                       f'ADD COLUMN "{column.name}" {col_type}')
                literal = _default_literal(column)
                if literal is not None:
                    # SQLite backfills existing rows with a constant DEFAULT.
                    ddl += f" DEFAULT {literal}"
                    if not column.nullable:
                        ddl += " NOT NULL"
                conn.exec_driver_sql(ddl)
                applied.append(ddl)
                log.info("Schema upgraded: %s", ddl)
    return applied
