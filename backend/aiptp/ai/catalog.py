"""Curated local-model catalog (PRD §18). Every entry is a real GGUF file on
Hugging Face with an honest hardware profile. New models are added here (or
later via the plugin registry) — the runtime accepts any chat-tuned GGUF."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ModelProfile:
    id: str
    name: str
    version: str
    parameters: str
    quantization: str
    disk_gb: float
    min_ram_gb: float
    recommended_ram_gb: float
    gpu_vram_gb: float  # recommended for full offload; 0 = CPU-friendly
    est_speed: str  # rough tokens/sec class on consumer hardware
    features: tuple[str, ...]
    url: str
    filename: str

    def view(self) -> dict:
        return asdict(self)


CATALOG: dict[str, ModelProfile] = {
    m.id: m
    for m in [
        ModelProfile(
            id="qwen2.5-0.5b-instruct-q4",
            name="Qwen2.5 0.5B Instruct",
            version="2.5",
            parameters="0.5B",
            quantization="Q4_K_M",
            disk_gb=0.5,
            min_ram_gb=1.5,
            recommended_ram_gb=4,
            gpu_vram_gb=0,
            est_speed="fast (20-60 tok/s CPU)",
            features=("chat", "json-output", "low-resource"),
            url="https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf",
            filename="qwen2.5-0.5b-instruct-q4_k_m.gguf",
        ),
        ModelProfile(
            id="llama-3.2-1b-instruct-q4",
            name="Llama 3.2 1B Instruct",
            version="3.2",
            parameters="1B",
            quantization="Q4_K_M",
            disk_gb=0.81,
            min_ram_gb=2.5,
            recommended_ram_gb=6,
            gpu_vram_gb=2,
            est_speed="fast (15-40 tok/s CPU)",
            features=("chat", "json-output"),
            url="https://huggingface.co/bartowski/Llama-3.2-1B-Instruct-GGUF/resolve/main/Llama-3.2-1B-Instruct-Q4_K_M.gguf",
            filename="Llama-3.2-1B-Instruct-Q4_K_M.gguf",
        ),
        ModelProfile(
            id="llama-3.2-3b-instruct-q4",
            name="Llama 3.2 3B Instruct",
            version="3.2",
            parameters="3B",
            quantization="Q4_K_M",
            disk_gb=2.0,
            min_ram_gb=5,
            recommended_ram_gb=8,
            gpu_vram_gb=4,
            est_speed="medium (8-20 tok/s CPU)",
            features=("chat", "json-output", "better-reasoning"),
            url="https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q4_K_M.gguf",
            filename="Llama-3.2-3B-Instruct-Q4_K_M.gguf",
        ),
        ModelProfile(
            id="qwen2.5-7b-instruct-q4",
            name="Qwen2.5 7B Instruct",
            version="2.5",
            parameters="7B",
            quantization="Q4_K_M",
            disk_gb=4.7,
            min_ram_gb=8,
            recommended_ram_gb=16,
            gpu_vram_gb=6,
            est_speed="slower (3-10 tok/s CPU, fast on GPU)",
            features=("chat", "json-output", "strong-reasoning"),
            url="https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q4_k_m.gguf",
            filename="qwen2.5-7b-instruct-q4_k_m.gguf",
        ),
    ]
}
