"""M4 local AI: grounded assistant, recommendation queue, guardrails,
model management endpoints (fake runtime — no real model in CI)."""

import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from aiptp.ai.manager import ModelManager
from aiptp.ai.runtime import FakeRuntime
from aiptp.config import Settings
from aiptp.main import create_app
from aiptp.marketdata.fake import FakeProvider
from aiptp.marketdata.service import MarketDataService

GOOD_RESPONSE = json.dumps({
    "analysis": "The portfolio is heavily concentrated in AAPL (100% of positions) "
                "with a diversification score reflecting that concentration.",
    "suggestions": [
        {"action": "SELL", "symbol": "AAPL", "notional": 500,
         "rationale": "Trim the concentrated AAPL position", "confidence": 0.7},
        {"action": "BUY", "symbol": "HACKED", "notional": 99999,
         "rationale": "ungrounded symbol must be dropped", "confidence": 0.9},
        {"action": "HOLD", "symbol": "", "notional": None,
         "rationale": "Keep remaining cash ready", "confidence": 0.6},
    ],
})


@pytest.fixture
def ai_setup(tmp_path):
    fake_provider = FakeProvider({"AAPL": "200", "MSFT": "400", "SPY": "500"})
    runtime = FakeRuntime(GOOD_RESPONSE)
    runtime.load("qwen2.5-0.5b-instruct-q4", None)
    manager = ModelManager(tmp_path / "models", runtime=runtime)
    cfg = Settings(db_url=f"sqlite:///{tmp_path / 'ai.db'}", data_dir=tmp_path,
                   market_providers="fake")
    market = MarketDataService([fake_provider], quote_ttl=0, history_ttl=0)
    app = create_app(cfg, market=market, model_manager=manager)
    with TestClient(app) as client:
        pid = client.post(
            "/api/v1/portfolios", json={"name": "AI Test", "starting_balance": "10000"}
        ).json()["id"]
        client.post(
            f"/api/v1/portfolios/{pid}/orders",
            json={"symbol": "AAPL", "side": "BUY", "type": "MARKET", "quantity": "10"},
        )
        yield client, pid, runtime, fake_provider


def test_hardware_and_models_endpoints(ai_setup):
    client, pid, runtime, _ = ai_setup
    hw = client.get("/api/v1/ai/hardware").json()
    assert hw["cpu_count"] >= 1
    assert hw["runtime_kind"] == "FakeRuntime"

    models = client.get("/api/v1/ai/models").json()
    ids = [m["id"] for m in models["models"]]
    assert "qwen2.5-0.5b-instruct-q4" in ids
    profile = next(m for m in models["models"] if m["id"] == "qwen2.5-0.5b-instruct-q4")
    for field in ("parameters", "quantization", "disk_gb", "min_ram_gb",
                  "recommended_ram_gb", "gpu_vram_gb", "est_speed", "hardware_fit"):
        assert field in profile
    assert "informational" in models["disclaimer"]


def test_analyze_grounding_and_review_queue(ai_setup):
    client, pid, runtime, _ = ai_setup
    result = client.post(f"/api/v1/portfolios/{pid}/ai/analyze", json={}).json()
    assert "concentrated" in result["analysis"]
    assert result["dropped_ungrounded"] == 1  # HACKED symbol was dropped
    assert len(result["recommendations"]) == 2  # SELL AAPL + HOLD
    assert result["auto_executed"] == []  # auto-execute is off by default
    # the model saw the real context pack
    pack = json.loads(runtime.last_user)
    assert pack["holdings"][0]["symbol"] == "AAPL"

    recs = client.get(f"/api/v1/portfolios/{pid}/ai/recommendations").json()
    sell = next(r for r in recs if r["action"] == "SELL")
    assert sell["status"] == "PENDING"
    assert sell["sizing"] == {"notional": "500.00"}
    assert sell["expected_impact"]["cash_after"] == "8500.00"  # 8000 + 500
    snapshot_ok = client.get(
        f"/api/v1/portfolios/{pid}/ai/recommendations"
    ).json()[0]["created_at"]
    assert snapshot_ok

    # approve executes at real (fake-provider) price with AI_ASSISTED origin
    out = client.post(
        f"/api/v1/portfolios/{pid}/ai/recommendations/{sell['id']}/approve"
    ).json()
    assert out["outcome"]["status"] == "EXECUTED"
    txns = client.get(f"/api/v1/portfolios/{pid}/transactions").json()
    assert txns[0]["origin"] == "AI_ASSISTED"
    assert Decimal(txns[0]["quantity"]) == Decimal("2.5")  # 500 / 200

    # double-approve refused
    assert client.post(
        f"/api/v1/portfolios/{pid}/ai/recommendations/{sell['id']}/approve"
    ).status_code == 409


def test_reject_flow(ai_setup):
    client, pid, runtime, _ = ai_setup
    client.post(f"/api/v1/portfolios/{pid}/ai/analyze", json={})
    rec = client.get(
        f"/api/v1/portfolios/{pid}/ai/recommendations?status=PENDING"
    ).json()[0]
    rejected = client.post(
        f"/api/v1/portfolios/{pid}/ai/recommendations/{rec['id']}/reject"
    ).json()
    assert rejected["status"] == "REJECTED"
    txns = client.get(f"/api/v1/portfolios/{pid}/transactions").json()
    assert all(t["origin"] != "AI_ASSISTED" for t in txns)


def test_auto_execute_with_guardrails(ai_setup):
    client, pid, runtime, _ = ai_setup
    client.put(
        f"/api/v1/portfolios/{pid}/ai/settings",
        json={"ai_auto_execute": True, "ai_max_trade_notional": "300",
              "ai_max_trades_per_day": 1},
    )
    result = client.post(f"/api/v1/portfolios/{pid}/ai/analyze", json={}).json()
    executed = [e for e in result["auto_executed"] if e["status"] == "EXECUTED"]
    assert len(executed) == 1
    txns = client.get(f"/api/v1/portfolios/{pid}/transactions").json()
    auto = next(t for t in txns if t["origin"] == "AI_AUTO")
    # notional clamped from 500 to the 300 guardrail: 300/200 = 1.5 shares
    assert Decimal(auto["quantity"]) == Decimal("1.5")

    # daily cap: a second analysis executes nothing
    result2 = client.post(f"/api/v1/portfolios/{pid}/ai/analyze", json={}).json()
    assert all(e["status"] != "EXECUTED" for e in result2["auto_executed"])
    assert any("cap" in (e.get("reason") or "") for e in result2["auto_executed"])


def test_malformed_model_output_degrades_gracefully(ai_setup):
    client, pid, runtime, _ = ai_setup
    runtime.response = "I think you should buy everything!!! not json"
    result = client.post(f"/api/v1/portfolios/{pid}/ai/analyze", json={}).json()
    assert result["recommendations"] == []
    assert "buy everything" in result["analysis"]


def test_default_model_and_settings(ai_setup):
    client, pid, runtime, _ = ai_setup
    assert client.put(
        "/api/v1/ai/default-model", json={"model_id": "llama-3.2-1b-instruct-q4"}
    ).json()["default_model"] == "llama-3.2-1b-instruct-q4"
    assert client.get("/api/v1/ai/models").json()["default_model"] == "llama-3.2-1b-instruct-q4"
    assert client.put(
        "/api/v1/ai/default-model", json={"model_id": "bogus"}
    ).status_code == 404

    settings = client.get(f"/api/v1/portfolios/{pid}/ai/settings").json()
    assert settings["ai_auto_execute"] is False
    assert settings["ai_max_trade_notional"] == "1000"


def test_benchmark_endpoint(ai_setup, tmp_path):
    client, pid, runtime, _ = ai_setup
    # fake runtime reports installed=False for all catalog entries
    resp = client.post("/api/v1/ai/models/qwen2.5-0.5b-instruct-q4/benchmark")
    assert resp.status_code == 409  # not installed
