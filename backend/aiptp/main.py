import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__
from .ai.manager import ModelManager
from .api import (
    admin,
    ai as ai_api,
    analytics,
    auth as auth_api,
    automation,
    marketdata,
    notifications,
    orders,
    plans,
    portfolios,
    strategies,
    watchlists,
    ws,
)
from .automation.engine import run_scheduled_rules_cycle
from .config import Settings, settings
from .core.events import EventBus
from .marketdata.alphavantage import AlphaVantageProvider
from .marketdata.fake import FakeProvider
from .marketdata.service import MarketDataService
from .marketdata.stooq import StooqProvider
from .marketdata.yahoo import YahooProvider
from .security import auth as auth_service
from .security import credentials
from .security.backup import backup_database
from .storage.db import Base, make_engine, make_session_factory
from .trading.corporate import run_corporate_actions_cycle
from .trading.recurring import run_recurring_cycle
from .watcher import run_watch_cycle

log = logging.getLogger(__name__)


class SPAStaticFiles(StaticFiles):
    """Serves the built frontend; unknown paths fall back to index.html so
    client-side routes (/portfolios/…, /companies/…) survive deep links."""

    async def get_response(self, path: str, scope):
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            return await super().get_response("index.html", scope)
        if response.status_code == 404:
            response = await super().get_response("index.html", scope)
        return response


def build_market(cfg: Settings, session_factory=None) -> MarketDataService:
    def alphavantage_key() -> str:
        if cfg.alphavantage_key:
            return cfg.alphavantage_key
        if session_factory is not None:
            with session_factory() as session:
                return credentials.load_key(session, cfg.data_dir, "alphavantage") or ""
        return ""

    providers = []
    names = [p.strip().lower() for p in cfg.market_providers.split(",") if p.strip()]
    # A stored (encrypted) key auto-appends Alpha Vantage to the chain even if
    # it isn't listed explicitly.
    if "alphavantage" not in names and session_factory is not None and alphavantage_key():
        names.append("alphavantage")
    for name in names:
        if name == "yahoo":
            providers.append(YahooProvider())
        elif name == "stooq":
            providers.append(StooqProvider())
        elif name == "alphavantage":
            key = alphavantage_key()
            if key:
                providers.append(AlphaVantageProvider(key))
            else:
                log.warning("alphavantage in provider chain but no key configured — skipping")
        elif name == "fake":
            providers.append(FakeProvider())
        else:
            log.warning("Unknown market provider %r — skipping", name)
    if not providers:
        providers = [YahooProvider(), StooqProvider()]
    return MarketDataService(
        providers, quote_ttl=cfg.quote_ttl_seconds, history_ttl=cfg.history_ttl_seconds
    )


def create_app(
    cfg: Settings | None = None,
    market: MarketDataService | None = None,
    model_manager: ModelManager | None = None,
) -> FastAPI:
    cfg = cfg or settings
    engine = make_engine(cfg.resolved_db_url())
    Base.metadata.create_all(engine)
    session_factory = make_session_factory(engine)
    market = market or build_market(cfg, session_factory)
    model_manager = model_manager or ModelManager(cfg.data_dir / "models")
    bus = EventBus()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        bus.bind_loop(asyncio.get_running_loop())
        scheduler = BackgroundScheduler()
        scheduler.add_job(
            run_watch_cycle,
            "interval",
            seconds=cfg.watch_interval_seconds,
            args=[session_factory, market, bus],
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            run_recurring_cycle,
            "interval",
            seconds=60,
            args=[session_factory, market, bus],
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            run_corporate_actions_cycle,
            "interval",
            hours=6,
            next_run_time=datetime.now() + timedelta(seconds=45),
            args=[session_factory, market, bus],
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            run_scheduled_rules_cycle,
            "interval",
            seconds=60,
            args=[session_factory, market, bus],
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            backup_database,
            "interval",
            hours=cfg.backup_interval_hours,
            next_run_time=datetime.now() + timedelta(minutes=2),
            args=[cfg.resolved_db_url(), cfg.data_dir],
            max_instances=1,
            coalesce=True,
        )
        scheduler.start()
        log.info("AIPTP %s started (provider=%s, watch every %ss)",
                 __version__, market.provider.name, cfg.watch_interval_seconds)
        yield
        scheduler.shutdown(wait=False)

    app = FastAPI(title="AIPTP", version=__version__, lifespan=lifespan)
    app.state.session_factory = session_factory
    app.state.market = market
    app.state.bus = bus
    app.state.settings = cfg
    app.state.model_manager = model_manager

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # Vite dev server
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Session-cookie auth for server mode. Public: auth endpoints, health,
    # and the static frontend (which needs to render the login screen).
    AUTH_EXEMPT_PREFIXES = ("/api/v1/auth/", "/api/v1/health")

    @app.middleware("http")
    async def auth_middleware(request, call_next):
        if cfg.auth == "required" and request.url.path.startswith("/api/v1"):
            if not request.url.path.startswith(AUTH_EXEMPT_PREFIXES):
                token = request.cookies.get(auth_service.SESSION_COOKIE)
                user = None
                if token:
                    with session_factory() as session:
                        user = auth_service.user_for_token(session, token)
                        session.commit()
                if user is None:
                    from fastapi.responses import JSONResponse

                    return JSONResponse(
                        status_code=401, content={"detail": "Authentication required"}
                    )
                request.state.user = user
                request.state.username = user.username
        return await call_next(request)

    api_prefix = "/api/v1"
    app.include_router(portfolios.router, prefix=api_prefix)
    app.include_router(portfolios.symbols_router, prefix=api_prefix)
    app.include_router(orders.router, prefix=api_prefix)
    app.include_router(plans.router, prefix=api_prefix)
    app.include_router(watchlists.router, prefix=api_prefix)
    app.include_router(analytics.router, prefix=api_prefix)
    app.include_router(automation.router, prefix=api_prefix)
    app.include_router(ai_api.router, prefix=api_prefix)
    app.include_router(ai_api.prouter, prefix=api_prefix)
    app.include_router(strategies.router, prefix=api_prefix)
    app.include_router(strategies.whatif_router, prefix=api_prefix)
    app.include_router(notifications.router, prefix=api_prefix)
    app.include_router(auth_api.router, prefix=api_prefix)
    app.include_router(admin.router, prefix=api_prefix)
    app.include_router(marketdata.router, prefix=api_prefix)
    app.include_router(ws.router, prefix=api_prefix)

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok", "version": __version__, "provider": market.provider.name}

    # Serve the built frontend when present (single-binary style deployment).
    if cfg.frontend_dir:
        frontend_dist = Path(cfg.frontend_dir)
    else:
        frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if frontend_dist.is_dir():
        app.mount("/", SPAStaticFiles(directory=frontend_dist, html=True), name="frontend")

    return app


def run() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(create_app(), host=settings.host, port=settings.port)


if __name__ == "__main__":
    run()
