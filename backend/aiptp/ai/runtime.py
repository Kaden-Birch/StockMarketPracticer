"""Model runtimes. The interface is tiny so alternative backends (Ollama
bridge, remote runners) can plug in later; llama.cpp is the built-in one.
Inference is serialized behind a lock — one model, one request at a time,
and it never blocks the API/watcher (callers run it in a worker thread)."""

import logging
import threading
import time
from pathlib import Path
from typing import Protocol

log = logging.getLogger(__name__)


class ModelRuntime(Protocol):
    model_id: str | None

    def load(self, model_id: str, model_path: Path) -> None: ...

    def unload(self) -> None: ...

    def generate(self, system: str, user: str, max_tokens: int = 1024) -> str: ...


class LlamaCppRuntime:
    """llama.cpp via llama-cpp-python. GPU layers offload automatically when
    the wheel was built with CUDA/Metal/Vulkan; plain CPU otherwise."""

    def __init__(self, n_ctx: int = 8192, n_gpu_layers: int = -1):
        self._llm = None
        self.model_id: str | None = None
        self._n_ctx = n_ctx
        self._n_gpu_layers = n_gpu_layers
        self._lock = threading.Lock()

    @staticmethod
    def available() -> bool:
        try:
            import llama_cpp  # noqa: F401

            return True
        except ImportError:
            return False

    def load(self, model_id: str, model_path: Path) -> None:
        from llama_cpp import Llama

        with self._lock:
            self.unload_locked()
            log.info("Loading model %s from %s", model_id, model_path)
            self._llm = Llama(
                model_path=str(model_path),
                n_ctx=self._n_ctx,
                n_gpu_layers=self._n_gpu_layers,
                verbose=False,
            )
            self.model_id = model_id

    def unload(self) -> None:
        with self._lock:
            self.unload_locked()

    def unload_locked(self) -> None:
        if self._llm is not None:
            del self._llm
            self._llm = None
            self.model_id = None

    def generate(self, system: str, user: str, max_tokens: int = 1024) -> str:
        with self._lock:
            if self._llm is None:
                raise RuntimeError("No model loaded")
            result = self._llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=max_tokens,
                temperature=0.2,
                repeat_penalty=1.15,  # small models loop without this
            )
            return result["choices"][0]["message"]["content"]

    def benchmark(self, prompt: str = "Explain diversification in one paragraph.") -> dict:
        with self._lock:
            if self._llm is None:
                raise RuntimeError("No model loaded")
            start = time.monotonic()
            result = self._llm.create_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=128,
                temperature=0.0,
            )
            elapsed = time.monotonic() - start
            completion_tokens = result.get("usage", {}).get("completion_tokens", 0)
            return {
                "model_id": self.model_id,
                "elapsed_seconds": round(elapsed, 2),
                "completion_tokens": completion_tokens,
                "tokens_per_second": round(completion_tokens / elapsed, 2) if elapsed else None,
            }


class FakeRuntime:
    """Deterministic runtime for tests: returns a canned response set by the
    test. Never used in real deployments."""

    def __init__(self, response: str = "{}"):
        self.model_id: str | None = None
        self.response = response
        self.last_system = ""
        self.last_user = ""

    def load(self, model_id: str, model_path: Path) -> None:
        self.model_id = model_id

    def unload(self) -> None:
        self.model_id = None

    def generate(self, system: str, user: str, max_tokens: int = 1024) -> str:
        self.last_system = system
        self.last_user = user
        return self.response

    def benchmark(self, prompt: str = "") -> dict:
        return {"model_id": self.model_id, "elapsed_seconds": 0.01,
                "completion_tokens": 42, "tokens_per_second": 4200.0}
