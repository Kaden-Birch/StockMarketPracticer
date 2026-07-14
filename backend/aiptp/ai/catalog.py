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
            url="https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF/resolve/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf",
            filename="Qwen2.5-7B-Instruct-Q4_K_M.gguf",
        ),
        ModelProfile(
            id="qwen2.5-3b-instruct-q4",
            name="Qwen2.5 3B Instruct",
            version="2.5", parameters="3B", quantization="Q4_K_M",
            disk_gb=1.93, min_ram_gb=4, recommended_ram_gb=8, gpu_vram_gb=3,
            est_speed="medium (10-25 tok/s CPU)",
            features=("chat", "json-output", "better-reasoning"),
            url="https://huggingface.co/bartowski/Qwen2.5-3B-Instruct-GGUF/resolve/main/Qwen2.5-3B-Instruct-Q4_K_M.gguf",
            filename="Qwen2.5-3B-Instruct-Q4_K_M.gguf",
        ),
        ModelProfile(
            id="smollm2-1.7b-instruct-q4",
            name="SmolLM2 1.7B Instruct",
            version="2", parameters="1.7B", quantization="Q4_K_M",
            disk_gb=1.06, min_ram_gb=3, recommended_ram_gb=6, gpu_vram_gb=2,
            est_speed="fast (15-35 tok/s CPU)",
            features=("chat", "low-resource"),
            url="https://huggingface.co/bartowski/SmolLM2-1.7B-Instruct-GGUF/resolve/main/SmolLM2-1.7B-Instruct-Q4_K_M.gguf",
            filename="SmolLM2-1.7B-Instruct-Q4_K_M.gguf",
        ),
        ModelProfile(
            id="gemma-2-2b-it-q4",
            name="Gemma 2 2B Instruct",
            version="2", parameters="2B", quantization="Q4_K_M",
            disk_gb=1.71, min_ram_gb=4, recommended_ram_gb=8, gpu_vram_gb=3,
            est_speed="fast (12-30 tok/s CPU)",
            features=("chat", "json-output"),
            url="https://huggingface.co/bartowski/gemma-2-2b-it-GGUF/resolve/main/gemma-2-2b-it-Q4_K_M.gguf",
            filename="gemma-2-2b-it-Q4_K_M.gguf",
        ),
        ModelProfile(
            id="phi-3.5-mini-instruct-q4",
            name="Phi 3.5 Mini Instruct",
            version="3.5", parameters="3.8B", quantization="Q4_K_M",
            disk_gb=2.39, min_ram_gb=5, recommended_ram_gb=8, gpu_vram_gb=4,
            est_speed="medium (8-20 tok/s CPU)",
            features=("chat", "json-output", "better-reasoning"),
            url="https://huggingface.co/bartowski/Phi-3.5-mini-instruct-GGUF/resolve/main/Phi-3.5-mini-instruct-Q4_K_M.gguf",
            filename="Phi-3.5-mini-instruct-Q4_K_M.gguf",
        ),
        ModelProfile(
            id="mistral-7b-instruct-v0.3-q4",
            name="Mistral 7B Instruct v0.3",
            version="0.3", parameters="7B", quantization="Q4_K_M",
            disk_gb=4.37, min_ram_gb=8, recommended_ram_gb=16, gpu_vram_gb=6,
            est_speed="slower on CPU, fast on GPU",
            features=("chat", "json-output", "strong-reasoning"),
            url="https://huggingface.co/bartowski/Mistral-7B-Instruct-v0.3-GGUF/resolve/main/Mistral-7B-Instruct-v0.3-Q4_K_M.gguf",
            filename="Mistral-7B-Instruct-v0.3-Q4_K_M.gguf",
        ),
        ModelProfile(
            id="llama-3.1-8b-instruct-q4",
            name="Llama 3.1 8B Instruct",
            version="3.1", parameters="8B", quantization="Q4_K_M",
            disk_gb=4.92, min_ram_gb=10, recommended_ram_gb=16, gpu_vram_gb=6,
            est_speed="slower on CPU, fast on GPU",
            features=("chat", "json-output", "strong-reasoning"),
            url="https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF/resolve/main/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
            filename="Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
        ),
        ModelProfile(
            id="gemma-2-9b-it-q4",
            name="Gemma 2 9B Instruct",
            version="2", parameters="9B", quantization="Q4_K_M",
            disk_gb=5.76, min_ram_gb=11, recommended_ram_gb=16, gpu_vram_gb=8,
            est_speed="slower on CPU, fast on GPU",
            features=("chat", "json-output", "strong-reasoning"),
            url="https://huggingface.co/bartowski/gemma-2-9b-it-GGUF/resolve/main/gemma-2-9b-it-Q4_K_M.gguf",
            filename="gemma-2-9b-it-Q4_K_M.gguf",
        ),
        ModelProfile(
            id="deepseek-r1-distill-qwen-7b-q4",
            name="DeepSeek R1 Distill Qwen 7B",
            version="R1", parameters="7B", quantization="Q4_K_M",
            disk_gb=4.68, min_ram_gb=8, recommended_ram_gb=16, gpu_vram_gb=6,
            est_speed="slower on CPU, fast on GPU (verbose reasoner)",
            features=("chat", "reasoning-traces"),
            url="https://huggingface.co/bartowski/DeepSeek-R1-Distill-Qwen-7B-GGUF/resolve/main/DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf",
            filename="DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf",
        ),
        ModelProfile(
            id="qwen2.5-14b-instruct-q4",
            name="Qwen2.5 14B Instruct",
            version="2.5", parameters="14B", quantization="Q4_K_M",
            disk_gb=8.99, min_ram_gb=16, recommended_ram_gb=24, gpu_vram_gb=12,
            est_speed="GPU strongly recommended",
            features=("chat", "json-output", "strong-reasoning"),
            url="https://huggingface.co/bartowski/Qwen2.5-14B-Instruct-GGUF/resolve/main/Qwen2.5-14B-Instruct-Q4_K_M.gguf",
            filename="Qwen2.5-14B-Instruct-Q4_K_M.gguf",
        ),
    ]
}
