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
    marketdata,
    modules as modules_api,
    orders,
    portfolios,
    strategies,
    watchlists,
    ws,
)
from .config import Settings, settings
from .core.events import EventBus
from .core.modules import AppContext, ModuleManager
from .marketdata.alphavantage import AlphaVantageProvider
from .marketdata.fake import FakeProvider
from .marketdata.service import MarketDataService
from .marketdata.stooq import StooqProvider
from .marketdata.yahoo import YahooProvider
from .modules import build_modules
from .security import auth as auth_service
from .security import credentials
from .security.backup import backup_database
from .storage.db import Base, make_engine, make_session_factory
from .trading.corporate import run_corporate_actions_cycle
from .watcher import run_watch_cycle

log = logging.getLogger(__name__)


class SPAStaticFiles(StaticFiles):
    """Serves the built frontend; unknown paths fall back to index.html so
    client-side routes (/portfolios/…, /companies/…) survive deep links.
    API paths never fall through — an unmatched /api/ route (e.g. a disabled
    module's endpoint) must be a real JSON 404, not the SPA HTML."""

    async def get_response(self, path: str, scope):
        is_api = path.startswith("api/") or path == "api"
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or is_api:
                raise
            return await super().get_response("index.html", scope)
        if response.status_code == 404 and not is_api:
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
    if model_manager is None:
        from .ai.manager import build_runtime

        model_manager = ModelManager(cfg.data_dir / "models", runtime=build_runtime(cfg))
    bus = EventBus()

    scheduler_jobs: list = []  # modules append (fn, trigger_kwargs, args, owner)

    def _isolated(fn, owner: str):
        """Module jobs must never take the scheduler down (roadmap 6.11.7)."""

        def wrapper(*args):
            try:
                fn(*args)
            except Exception:  # noqa: BLE001
                log.exception("Scheduled job %s (module %s) failed — isolated",
                              getattr(fn, "__name__", fn), owner)

        wrapper.__name__ = f"{owner}:{getattr(fn, '__name__', 'job')}"
        return wrapper

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        bus.bind_loop(asyncio.get_running_loop())
        scheduler = BackgroundScheduler()
        # Core platform jobs
        scheduler.add_job(
            run_watch_cycle,
            "interval",
            seconds=cfg.watch_interval_seconds,
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
            backup_database,
            "interval",
            hours=cfg.backup_interval_hours,
            next_run_time=datetime.now() + timedelta(minutes=2),
            args=[cfg.resolved_db_url(), cfg.data_dir],
            max_instances=1,
            coalesce=True,
        )
        # Module-contributed jobs (registered by running modules only)
        for fn, trigger_kwargs, args, owner in scheduler_jobs:
            scheduler.add_job(
                _isolated(fn, owner), args=args, max_instances=1, coalesce=True,
                **trigger_kwargs,
            )
        scheduler.start()
        log.info("AIPTP %s started (provider=%s, watch every %ss, %d module jobs)",
                 __version__, market.provider.name, cfg.watch_interval_seconds,
                 len(scheduler_jobs))
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

    # ---- Core Platform routers (roadmap 6.11.1) ----
    api_prefix = "/api/v1"
    app.include_router(portfolios.router, prefix=api_prefix)
    app.include_router(portfolios.symbols_router, prefix=api_prefix)
    app.include_router(orders.router, prefix=api_prefix)
    app.include_router(watchlists.router, prefix=api_prefix)
    app.include_router(analytics.router, prefix=api_prefix)
    app.include_router(ai_api.router, prefix=api_prefix)  # model manager = core
    app.include_router(strategies.router, prefix=api_prefix)
    app.include_router(strategies.whatif_router, prefix=api_prefix)
    app.include_router(auth_api.router, prefix=api_prefix)
    app.include_router(admin.router, prefix=api_prefix)
    app.include_router(modules_api.router, prefix=api_prefix)
    app.include_router(marketdata.router, prefix=api_prefix)
    app.include_router(ws.router, prefix=api_prefix)

    # ---- Optional modules (roadmap 6.11.2): everything else registers
    # itself through the ModuleManager; failures are isolated. ----
    ctx = AppContext(
        app=app,
        session_factory=session_factory,
        market=market,
        bus=bus,
        settings=cfg,
        model_manager=model_manager,
        scheduler_jobs=scheduler_jobs,
    )
    module_manager = ModuleManager(ctx)
    app.state.module_manager = module_manager
    module_manager.register_all(build_modules())

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
