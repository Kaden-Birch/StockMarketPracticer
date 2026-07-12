"""Model manager (PRD §19): hardware detection, install/remove, hot
switching, benchmark, hardware-fit recommendations."""

import logging
import os
import shutil
import subprocess
import threading
from pathlib import Path

import httpx

from .catalog import CATALOG, ModelProfile
from .runtime import FakeRuntime, LlamaCppRuntime

log = logging.getLogger(__name__)


def detect_hardware() -> dict:
    ram_gb = None
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        ram_gb = round(pages * page_size / 1024**3, 1)
    except (ValueError, OSError):
        pass
    gpus = []
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=5,
            )
            for line in out.stdout.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 2:
                    gpus.append({"name": parts[0], "vram": parts[1]})
        except (subprocess.SubprocessError, OSError):
            pass
    return {
        "cpu_count": os.cpu_count(),
        "ram_gb": ram_gb,
        "gpus": gpus,
        "runtime_available": LlamaCppRuntime.available(),
    }


def fit_for_hardware(profile: ModelProfile, hardware: dict) -> str:
    """fits | marginal | too_large for the detected machine."""
    ram = hardware.get("ram_gb")
    if ram is None:
        return "unknown"
    if ram >= profile.recommended_ram_gb:
        return "fits"
    if ram >= profile.min_ram_gb:
        return "marginal"
    return "too_large"


class ModelManager:
    def __init__(self, models_dir: Path, runtime=None):
        self.models_dir = models_dir
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.runtime = runtime if runtime is not None else (
            LlamaCppRuntime() if LlamaCppRuntime.available() else FakeRuntime()
        )
        self.runtime_kind = type(self.runtime).__name__
        self._download_lock = threading.Lock()
        self.download_progress: dict[str, dict] = {}  # model_id -> {done, total}

    # ---- inventory ----

    def path_for(self, model_id: str) -> Path:
        profile = CATALOG.get(model_id)
        if profile is None:
            raise KeyError(f"Unknown model: {model_id}")
        return self.models_dir / profile.filename

    def installed(self, model_id: str) -> bool:
        try:
            return self.path_for(model_id).exists()
        except KeyError:
            return False

    def catalog_view(self) -> list[dict]:
        hardware = detect_hardware()
        out = []
        for profile in CATALOG.values():
            view = profile.view()
            view["installed"] = self.installed(profile.id)
            view["loaded"] = self.runtime.model_id == profile.id
            view["hardware_fit"] = fit_for_hardware(profile, hardware)
            view["download"] = self.download_progress.get(profile.id)
            out.append(view)
        return out

    # ---- lifecycle ----

    def download(self, model_id: str) -> Path:
        """Blocking download with progress tracking (callers run it in a
        thread). Resumable via HTTP Range when partially present."""
        profile = CATALOG[model_id]
        target = self.path_for(model_id)
        partial = target.with_suffix(".part")
        with self._download_lock:
            if target.exists():
                return target
            headers = {}
            done = 0
            if partial.exists():
                done = partial.stat().st_size
                headers["Range"] = f"bytes={done}-"
            with httpx.stream(
                "GET", profile.url, headers=headers, follow_redirects=True, timeout=60
            ) as resp:
                if resp.status_code not in (200, 206):
                    raise RuntimeError(f"Download failed: HTTP {resp.status_code}")
                if resp.status_code == 200:
                    done = 0
                    mode = "wb"
                else:
                    mode = "ab"
                total = int(resp.headers.get("content-length", 0)) + done
                self.download_progress[model_id] = {"done": done, "total": total}
                with open(partial, mode) as f:
                    for chunk in resp.iter_bytes(1024 * 512):
                        f.write(chunk)
                        done += len(chunk)
                        self.download_progress[model_id] = {"done": done, "total": total}
            partial.rename(target)
            self.download_progress.pop(model_id, None)
            log.info("Model %s installed (%s)", model_id, target.name)
            return target

    def remove(self, model_id: str) -> bool:
        if self.runtime.model_id == model_id:
            self.runtime.unload()
        target = self.path_for(model_id)
        partial = target.with_suffix(".part")
        removed = False
        for p in (target, partial):
            if p.exists():
                p.unlink()
                removed = True
        return removed

    def load(self, model_id: str) -> None:
        """Hot switch: unloads whatever is loaded, loads the new model."""
        if not self.installed(model_id):
            raise FileNotFoundError(f"Model {model_id} is not installed")
        self.runtime.load(model_id, self.path_for(model_id))

    def benchmark(self, model_id: str) -> dict:
        if self.runtime.model_id != model_id:
            self.load(model_id)
        return self.runtime.benchmark()
