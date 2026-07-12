"""M3 automation engine: AST validation/evaluation, rule firing via the
watch cycle, edge triggering, cooldowns, actions, fire log."""

from decimal import Decimal

import pytest

from aiptp.automation import conditions


def run_cycle(client):
    from aiptp.watcher import run_watch_cycle

    app = client.app
    run_watch_cycle(app.state.session_factory, app.state.market, app.state.bus)


def make_rule(client, portfolio_id, **overrides):
    body = {
        "name": "Buy the dip",
        "trigger": {"price": {"symbol": "AAPL", "op": "<", "value": 190}},
        "action_type": "BUY",
        "action_params": {"symbol": "AAPL", "notional": "1000"},
        "cooldown_seconds": 0,
    }
    body.update(overrides)
    resp = client.post(f"/api/v1/portfolios/{portfolio_id}/rules", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---- AST unit tests ----

def test_validate_rejects_malformed():
    with pytest.raises(ValueError):
        conditions.validate_trigger({"price": {"symbol": "AAPL"}})  # no op/value
    with pytest.raises(ValueError):
        conditions.validate_trigger({"bogus": {}})
    with pytest.raises(ValueError):
        conditions.validate_trigger({"all": []})
    with pytest.raises(ValueError):
        conditions.validate_trigger({"schedule": {"at": "25:00"}})
    conditions.validate_trigger(  # valid nested AST
        {"all": [
            {"price": {"symbol": "AAPL", "op": "<", "value": 190}},
            {"not": {"cash": {"op": "<", "value": 500}}},
        ]}
    )


def test_referenced_symbols_and_schedule_detection():
    ast = {"any": [
        {"price": {"symbol": "aapl", "op": "<", "value": 1}},
        {"all": [{"indicator": {"symbol": "MSFT", "name": "RSI", "op": "<", "value": 30}},
                  {"schedule": {"at": "14:30"}}]},
    ]}
    assert conditions.referenced_symbols(ast) == {"AAPL", "MSFT"}
    assert conditions.has_schedule(ast) is True


# ---- end-to-end rule behavior ----

def test_rule_fires_on_price_and_edge_triggers(client, fake_provider, portfolio_id):
    rule = make_rule(client, portfolio_id)
    # price 200 > 190: no fire
    run_cycle(client)
    fires = client.get(f"/api/v1/portfolios/{portfolio_id}/rules/{rule['id']}/fires").json()
    assert fires == []

    fake_provider.set_price("AAPL", "185")
    run_cycle(client)
    fires = client.get(f"/api/v1/portfolios/{portfolio_id}/rules/{rule['id']}/fires").json()
    assert len(fires) == 1
    assert fires[0]["result"] == "EXECUTED"
    txns = client.get(f"/api/v1/portfolios/{portfolio_id}/transactions").json()
    assert txns[0]["origin"] == "AUTOMATION"

    # condition still true next cycle: edge triggering prevents a second fire
    run_cycle(client)
    fires = client.get(f"/api/v1/portfolios/{portfolio_id}/rules/{rule['id']}/fires").json()
    assert len(fires) == 1

    # condition releases, then re-triggers: fires again
    fake_provider.set_price("AAPL", "195")
    run_cycle(client)
    fake_provider.set_price("AAPL", "180")
    run_cycle(client)
    fires = client.get(f"/api/v1/portfolios/{portfolio_id}/rules/{rule['id']}/fires").json()
    assert len(fires) == 2

    # notification inbox recorded the fires
    inbox = client.get("/api/v1/notifications").json()
    assert inbox["unread_count"] >= 2
    assert any(n["type"] == "rule_fired" for n in inbox["notifications"])


def test_cooldown_blocks_refire(client, fake_provider, portfolio_id):
    rule = make_rule(client, portfolio_id, cooldown_seconds=3600)
    fake_provider.set_price("AAPL", "185")
    run_cycle(client)
    fake_provider.set_price("AAPL", "195")
    run_cycle(client)
    fake_provider.set_price("AAPL", "180")
    run_cycle(client)  # would refire, but cooldown blocks
    fires = client.get(f"/api/v1/portfolios/{portfolio_id}/rules/{rule['id']}/fires").json()
    assert len(fires) == 1


def test_sell_percent_action_and_notify_action(client, fake_provider, portfolio_id):
    client.post(
        f"/api/v1/portfolios/{portfolio_id}/orders",
        json={"symbol": "AAPL", "side": "BUY", "type": "MARKET", "quantity": "10"},
    )
    make_rule(
        client, portfolio_id,
        name="Take profit",
        trigger={"price": {"symbol": "AAPL", "op": ">", "value": 250}},
        action_type="SELL",
        action_params={"symbol": "AAPL", "percent": "50"},
    )
    make_rule(
        client, portfolio_id,
        name="Cash alert",
        trigger={"cash": {"op": "<", "value": 100000}},
        action_type="NOTIFY",
        action_params={"message": "Cash below threshold"},
    )
    fake_provider.set_price("AAPL", "260")
    run_cycle(client)
    holding = client.get(f"/api/v1/portfolios/{portfolio_id}").json()["holdings"][0]
    assert Decimal(holding["quantity"]) == 5  # sold 50%
    inbox = client.get("/api/v1/notifications").json()["notifications"]
    assert any("Cash below threshold" in n["body"] for n in inbox)


def test_insufficient_cash_fire_logged_as_rejected(client, fake_provider, portfolio_id):
    rule = make_rule(client, portfolio_id,
                     action_params={"symbol": "AAPL", "notional": "999999"})
    fake_provider.set_price("AAPL", "150")
    run_cycle(client)
    fires = client.get(f"/api/v1/portfolios/{portfolio_id}/rules/{rule['id']}/fires").json()
    assert fires[0]["result"] == "REJECTED"
    assert "Insufficient cash" in fires[0]["detail"]


def test_indicator_condition(client, fake_provider, portfolio_id):
    # flat fake history -> RSI is None (no gains/losses)? flat -> avg_loss 0 -> RSI 100.
    rule = make_rule(
        client, portfolio_id,
        name="RSI overbought",
        trigger={"indicator": {"symbol": "AAPL", "name": "RSI", "period": 14, "op": ">", "value": 90}},
        action_type="NOTIFY",
        action_params={"message": "RSI high"},
    )
    run_cycle(client)
    fires = client.get(f"/api/v1/portfolios/{portfolio_id}/rules/{rule['id']}/fires").json()
    assert len(fires) == 1 and fires[0]["result"] == "NOTIFIED"


def test_rule_crud_and_validation(client, portfolio_id):
    r = client.post(
        f"/api/v1/portfolios/{portfolio_id}/rules",
        json={"name": "bad", "trigger": {"nope": {}}, "action_type": "NOTIFY"},
    )
    assert r.status_code == 422
    r = client.post(
        f"/api/v1/portfolios/{portfolio_id}/rules",
        json={"name": "bad2",
              "trigger": {"price": {"symbol": "AAPL", "op": "<", "value": 1}},
              "action_type": "BUY", "action_params": {"symbol": "AAPL"}},
    )
    assert r.status_code == 422  # no sizing

    rule = make_rule(client, portfolio_id)
    r = client.patch(
        f"/api/v1/portfolios/{portfolio_id}/rules/{rule['id']}",
        json={"enabled": False, "name": "Renamed"},
    )
    assert r.json()["enabled"] is False and r.json()["name"] == "Renamed"
    assert client.delete(
        f"/api/v1/portfolios/{portfolio_id}/rules/{rule['id']}"
    ).status_code == 204
    assert client.get(f"/api/v1/portfolios/{portfolio_id}/rules").json() == []
