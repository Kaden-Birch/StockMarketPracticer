import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__
from .api import marketdata, orders, portfolios, ws
from .config import Settings, settings
from .core.events import EventBus
from .marketdata.fake import FakeProvider
from .marketdata.service import MarketDataService
from .marketdata.yahoo import YahooProvider
from .storage.db import Base, make_engine, make_session_factory
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


def build_market(cfg: Settings) -> MarketDataService:
    if cfg.market_provider == "fake":
        provider = FakeProvider()
    else:
        provider = YahooProvider()
    return MarketDataService(
        provider, quote_ttl=cfg.quote_ttl_seconds, history_ttl=cfg.history_ttl_seconds
    )


def create_app(cfg: Settings | None = None, market: MarketDataService | None = None) -> FastAPI:
    cfg = cfg or settings
    engine = make_engine(cfg.resolved_db_url())
    Base.metadata.create_all(engine)
    session_factory = make_session_factory(engine)
    market = market or build_market(cfg)
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
        scheduler.start()
        log.info("AIPTP %s started (provider=%s, watch every %ss)",
                 __version__, market.provider.name, cfg.watch_interval_seconds)
        yield
        scheduler.shutdown(wait=False)

    app = FastAPI(title="AIPTP", version=__version__, lifespan=lifespan)
    app.state.session_factory = session_factory
    app.state.market = market
    app.state.bus = bus

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # Vite dev server
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api_prefix = "/api/v1"
    app.include_router(portfolios.router, prefix=api_prefix)
    app.include_router(orders.router, prefix=api_prefix)
    app.include_router(marketdata.router, prefix=api_prefix)
    app.include_router(ws.router, prefix=api_prefix)

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok", "version": __version__, "provider": market.provider.name}

    # Serve the built frontend when present (single-binary style deployment).
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
