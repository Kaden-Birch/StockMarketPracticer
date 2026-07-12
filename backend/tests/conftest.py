import pytest
from fastapi.testclient import TestClient

from aiptp.config import Settings
from aiptp.main import create_app
from aiptp.marketdata.fake import FakeProvider
from aiptp.marketdata.service import MarketDataService


@pytest.fixture
def fake_provider() -> FakeProvider:
    return FakeProvider({"AAPL": "200", "MSFT": "400", "NVDA": "150"})


@pytest.fixture
def client(tmp_path, fake_provider) -> TestClient:
    cfg = Settings(db_url=f"sqlite:///{tmp_path / 'test.db'}", market_providers="fake")
    market = MarketDataService([fake_provider], quote_ttl=0, history_ttl=0)
    app = create_app(cfg, market=market)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def portfolio_id(client) -> str:
    resp = client.post(
        "/api/v1/portfolios",
        json={"name": "Test", "starting_balance": "10000"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]
