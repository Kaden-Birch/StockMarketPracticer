"""Automatic in-place schema upgrade for pre-1.0 SQLite databases: a
database created by an older version (missing the M7/M8 portfolio columns)
must boot, upgrade, and serve its existing data — never crash with
'no such column' and never require deleting the data directory."""

import sqlite3

from fastapi.testclient import TestClient

from aiptp.config import Settings
from aiptp.main import create_app
from aiptp.marketdata.fake import FakeProvider
from aiptp.marketdata.service import MarketDataService


def _make_old_database(path: str) -> None:
    """A portfolios table as it looked before M7 (no owner /
    public_on_leaderboard / mandate / scenario_session_id), with one real
    portfolio in it — mirroring the user-reported failure."""
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE portfolios (
            id VARCHAR(32) NOT NULL PRIMARY KEY,
            name VARCHAR(120) NOT NULL,
            description TEXT NOT NULL,
            currency VARCHAR(8) NOT NULL,
            starting_balance VARCHAR(40) NOT NULL,
            cash_balance VARCHAR(40) NOT NULL,
            cost_basis_method VARCHAR(7) NOT NULL,
            dividend_reinvest BOOLEAN NOT NULL,
            ai_auto_execute BOOLEAN NOT NULL,
            ai_max_trade_notional VARCHAR(40) NOT NULL,
            ai_max_trades_per_day INTEGER NOT NULL,
            ai_default_model VARCHAR(80) NOT NULL,
            mode VARCHAR(8) NOT NULL,
            preset VARCHAR(20) NOT NULL,
            game_xp INTEGER NOT NULL,
            ends_at DATETIME,
            notes TEXT NOT NULL,
            created_at DATETIME NOT NULL
        );
        INSERT INTO portfolios VALUES (
            'old1', 'Legacy portfolio', '', 'USD', '10000', '10000',
            'FIFO', 0, 0, '1000', 3, '', 'CLASSIC', 'ACADEMY', 0,
            NULL, '', '2025-01-01 00:00:00'
        );
        """
    )
    conn.commit()
    conn.close()


def test_old_database_upgrades_in_place_and_serves(tmp_path):
    db_path = tmp_path / "old.db"
    _make_old_database(str(db_path))

    cfg = Settings(db_url=f"sqlite:///{db_path}", data_dir=tmp_path,
                   market_providers="fake")
    market = MarketDataService([FakeProvider({"AAPL": "200"})], quote_ttl=0)
    with TestClient(create_app(cfg, market=market)) as c:
        # the pre-existing portfolio survives, with defaulted new columns
        portfolios = c.get("/api/v1/portfolios").json()
        assert [p["name"] for p in portfolios] == ["Legacy portfolio"]
        assert portfolios[0]["owner"] == "local"
        assert portfolios[0]["public_on_leaderboard"] is False

        # the exact queries that crashed on old databases now work
        assert c.get("/api/v1/leaderboards").status_code == 200
        from aiptp.watcher import watched_symbols

        with c.app.state.session_factory() as session:
            watched_symbols(session)  # was: no such column scenario_session_id

        # trading against the upgraded row still works end to end
        r = c.post("/api/v1/portfolios/old1/orders",
                   json={"symbol": "AAPL", "side": "BUY", "type": "MARKET",
                         "quantity": "5"})
        assert r.status_code == 201 and r.json()["status"] == "FILLED"

        # mandate column arrived usable too (M8)
        assert c.put("/api/v1/portfolios/old1/mandate",
                     json={"mandate": "growth"}).status_code == 200


def test_upgrade_is_idempotent(tmp_path):
    from aiptp.storage.db import Base, auto_upgrade, make_engine

    db_path = tmp_path / "old2.db"
    _make_old_database(str(db_path))
    engine = make_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    first = auto_upgrade(engine)
    assert any("scenario_session_id" in ddl for ddl in first)
    assert any("owner" in ddl for ddl in first)
    assert auto_upgrade(engine) == []  # second boot: nothing left to do
