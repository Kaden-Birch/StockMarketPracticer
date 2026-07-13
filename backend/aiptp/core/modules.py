"""Module / plugin framework (roadmap 6.11).

Every optional feature is a Module with a declarative manifest and a
standard lifecycle. The ModuleManager validates dependencies, registers
routers/jobs/event handlers with the core, cascades disables, and isolates
failures so one broken module never takes down the platform.

The Core Platform (trading, market data, portfolios, analytics, auth,
storage, AI model manager) never imports from modules; modules reach the
core only through the AppContext handed to them and through events.
"""

import enum
import logging
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger(__name__)


class Permission(str, enum.Enum):
    READ_PORTFOLIO = "ReadPortfolio"
    MODIFY_PORTFOLIO = "ModifyPortfolio"
    READ_COMPANY_DATA = "ReadCompanyData"
    SEND_NOTIFICATIONS = "SendNotifications"
    ACCESS_AI_MODELS = "AccessAIModels"
    ACCESS_MULTIPLAYER = "AccessMultiplayer"
    READ_HISTORICAL_DATA = "ReadHistoricalData"


class ModuleState(str, enum.Enum):
    REGISTERED = "REGISTERED"
    RUNNING = "RUNNING"
    DISABLED = "DISABLED"  # by user/preset or dependency cascade
    FAILED = "FAILED"  # crashed during lifecycle; isolated


@dataclass
class UiContribution:
    """A piece of UI a module adds; the frontend assembles itself from
    these (roadmap 6.11.12)."""

    kind: str  # nav_item | portfolio_tab | settings_page | dashboard_widget
    label: str
    path: str = ""  # route or anchor the frontend maps this to
    icon: str = ""


@dataclass
class Manifest:
    id: str
    name: str
    version: str
    description: str = ""
    dependencies: list[str] = field(default_factory=list)  # module ids
    permissions: list[Permission] = field(default_factory=list)
    events_published: list[str] = field(default_factory=list)
    events_consumed: list[str] = field(default_factory=list)
    settings: list[dict] = field(default_factory=list)  # {key,label,type,...}
    ui: list[UiContribution] = field(default_factory=list)


@dataclass
class AppContext:
    """Everything a module may touch. Modules must not import core internals
    directly beyond what this hands them."""

    app: Any  # FastAPI
    session_factory: Any
    market: Any
    bus: Any
    settings: Any
    model_manager: Any
    scheduler_jobs: list  # (fn, trigger_kwargs) — registered when scheduler starts


class Module:
    """Base class. Subclasses override lifecycle hooks as needed; every hook
    is called under the manager's error isolation."""

    manifest: Manifest

    def initialize(self, ctx: AppContext) -> None:  # wire routers, services
        pass

    def register_events(self, ctx: AppContext) -> None:  # bus subscriptions
        pass

    def start(self, ctx: AppContext) -> None:  # schedule jobs etc.
        pass

    def shutdown(self, ctx: AppContext) -> None:
        pass


MODULE_SETTING_PREFIX = "module."


def module_setting_key(module_id: str) -> str:
    return f"{MODULE_SETTING_PREFIX}{module_id}.enabled"


class ModuleManager:
    def __init__(self, ctx: AppContext):
        self.ctx = ctx
        self.modules: dict[str, Module] = {}
        self.states: dict[str, ModuleState] = {}
        self.errors: dict[str, str] = {}
        self.disabled_reasons: dict[str, str] = {}
        self._order: list[str] = []

    # ---- registration & lifecycle ----

    def register_all(self, modules: list[Module]) -> None:
        for module in modules:
            self.modules[module.manifest.id] = module
            self.states[module.manifest.id] = ModuleState.REGISTERED
        self._order = self._topological_order()
        user_disabled = self._user_disabled_ids()
        for module_id in self._order:
            module = self.modules[module_id]
            if module_id in user_disabled:
                self._disable(module_id, "disabled in settings")
                continue
            missing = [d for d in module.manifest.dependencies
                       if self.states.get(d) != ModuleState.RUNNING]
            if missing:
                self._disable(
                    module_id,
                    f"requires {', '.join(missing)} which is not running",
                )
                continue
            try:
                module.initialize(self.ctx)
                module.register_events(self.ctx)
                module.start(self.ctx)
                self.states[module_id] = ModuleState.RUNNING
                log.info("Module %s v%s running", module_id, module.manifest.version)
            except Exception:  # noqa: BLE001 — isolation is the contract
                self.states[module_id] = ModuleState.FAILED
                self.errors[module_id] = traceback.format_exc(limit=3)
                log.exception("Module %s failed to start — isolated", module_id)

    def _topological_order(self) -> list[str]:
        order: list[str] = []
        seen: set[str] = set()

        def visit(mid: str, stack: tuple = ()):
            if mid in seen or mid not in self.modules:
                return
            if mid in stack:
                raise ValueError(f"Dependency cycle involving {mid}")
            for dep in self.modules[mid].manifest.dependencies:
                visit(dep, stack + (mid,))
            seen.add(mid)
            order.append(mid)

        for mid in self.modules:
            visit(mid)
        return order

    def _user_disabled_ids(self) -> set[str]:
        from ..storage.models import AppSetting

        with self.ctx.session_factory() as session:
            disabled = set()
            for module_id in self.modules:
                setting = session.get(AppSetting, module_setting_key(module_id))
                if setting is not None and setting.value == "off":
                    disabled.add(module_id)
            return disabled

    def _disable(self, module_id: str, reason: str) -> None:
        self.states[module_id] = ModuleState.DISABLED
        self.disabled_reasons[module_id] = reason
        log.info("Module %s disabled: %s", module_id, reason)

    # ---- runtime state ----

    def is_running(self, module_id: str) -> bool:
        return self.states.get(module_id) == ModuleState.RUNNING

    def set_enabled(self, session, module_id: str, enabled: bool) -> None:
        """Persist the user's choice. Takes effect on restart (routers and
        scheduler jobs are wired at startup); status reports it immediately."""
        from ..storage.models import AppSetting

        if module_id not in self.modules:
            raise KeyError(module_id)
        key = module_setting_key(module_id)
        setting = session.get(AppSetting, key)
        if setting is None:
            setting = AppSetting(key=key)
            session.add(setting)
        setting.value = "on" if enabled else "off"

    def dependents_of(self, module_id: str) -> list[str]:
        return [
            mid for mid, m in self.modules.items()
            if module_id in m.manifest.dependencies
        ]

    def status(self, session=None) -> list[dict]:
        from ..storage.models import AppSetting

        out = []
        for module_id in self._order:
            module = self.modules[module_id]
            m = module.manifest
            pending = None
            if session is not None:
                setting = session.get(AppSetting, module_setting_key(module_id))
                wanted = "off" if setting is not None and setting.value == "off" else "on"
                actual = "on" if self.is_running(module_id) else "off"
                if wanted != actual and self.states[module_id] != ModuleState.FAILED:
                    pending = f"will be {wanted} after restart"
            out.append({
                "id": m.id,
                "name": m.name,
                "version": m.version,
                "description": m.description,
                "dependencies": m.dependencies,
                "permissions": [p.value for p in m.permissions],
                "events_published": m.events_published,
                "events_consumed": m.events_consumed,
                "settings": m.settings,
                "ui": [vars(c) for c in m.ui],
                "state": self.states[module_id].value,
                "disabled_reason": self.disabled_reasons.get(module_id),
                "error": self.errors.get(module_id),
                "pending_change": pending,
            })
        return out
