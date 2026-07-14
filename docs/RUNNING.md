# Running AIPTP on your machine

AIPTP is a Python 3.11+ backend (FastAPI) that serves the built React
frontend from one process on **http://localhost:8420**. Real market data
comes from Yahoo/Stooq with no API key. The local AI mentor/assistant uses
llama.cpp models (GGUF) and can use your GPU — Metal on Apple Silicon,
CUDA on Linux/NVIDIA.

---

## macOS (Apple Silicon or Intel)

### 1. Prerequisites

```bash
# Xcode command-line tools (compiler for the GPU build)
xcode-select --install

# Homebrew (if you don't have it): https://brew.sh
brew install python@3.12 node git
```

### 2. Get the code and build

```bash
git clone https://github.com/Kaden-Birch/StockMarketPracticer.git
cd StockMarketPracticer

# backend
python3 -m venv .venv
.venv/bin/pip install -e "backend[dev]"

# frontend (the server serves frontend/dist)
cd frontend && npm install && npm run build && cd ..
```

### 3. AI models with Metal GPU acceleration (Apple Silicon)

`llama-cpp-python` ships pre-built **Metal** wheels for Apple Silicon —
on M1/M2/M3/M4 the plain install is already GPU-accelerated:

```bash
.venv/bin/pip install llama-cpp-python
```

If it falls back to building from source (or you're on an Intel Mac and
want to force a specific build), compile with Metal explicitly:

```bash
CMAKE_ARGS="-DGGML_METAL=on" .venv/bin/pip install --no-cache-dir llama-cpp-python
```

### 4. Run

```bash
AIPTP_DATA_DIR=~/aiptp-data .venv/bin/python -m aiptp.main
```

Open **http://localhost:8420**. Desktop mode needs no login. Go to
**AI Models**, install a model from the catalog (start with
`qwen2.5-0.5b-instruct-q4`, 469 MB, to smoke-test; then something in the
3B–8B range — Apple Silicon handles them comfortably), press **Load**,
then **Benchmark**. With Metal active you'll see tokens/sec far above CPU
speeds; the log line `ggml_metal_init` on startup confirms the GPU is in
use.

---

## Linux (NVIDIA GPU with CUDA)

### 1. Prerequisites

- Python 3.11+, Node 18+, git, and a C/C++ toolchain
  (`sudo apt install python3-venv python3-dev nodejs npm git build-essential cmake` on Debian/Ubuntu)
- NVIDIA driver + CUDA Toolkit (verify with `nvidia-smi` and `nvcc --version`)

### 2. Get the code and build

```bash
git clone https://github.com/Kaden-Birch/StockMarketPracticer.git
cd StockMarketPracticer
python3 -m venv .venv
.venv/bin/pip install -e "backend[dev]"
cd frontend && npm install && npm run build && cd ..
```

### 3. AI models with CUDA GPU acceleration

Try the pre-built CUDA wheel first (fast, no compile — pick the index
matching your CUDA major version, e.g. cu121 / cu122 / cu124):

```bash
.venv/bin/pip install llama-cpp-python \
  --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124
```

Or compile against your exact CUDA install (10–20 minutes):

```bash
CMAKE_ARGS="-DGGML_CUDA=on" .venv/bin/pip install --no-cache-dir llama-cpp-python
```

### 4. Run

```bash
AIPTP_DATA_DIR=~/aiptp-data .venv/bin/python -m aiptp.main
```

Open **http://localhost:8420**, install/load a model under **AI Models**,
and benchmark. `nvidia-smi` while a model is loaded should show the
process holding VRAM — that's the GPU offload working (the runtime
requests full layer offload; a model that fits in VRAM runs entirely on
the GPU).

---

## Either OS: useful variants

| What | How |
|---|---|
| Different port | `AIPTP_PORT=9000 …` |
| Server mode (login required, multi-user) | `AIPTP_AUTH=required AIPTP_HOST=0.0.0.0 …` — first visit creates the admin account; add players in Settings → Users |
| Alpha Vantage as a third data provider | add your key in Settings → Market data providers (stored encrypted) |
| Docker instead of a local Python | `docker compose -f deploy/compose.yaml up` (CPU inference; GPU pass-through needs `--gpus all` and a CUDA base image — native install recommended for GPU) |
| Where everything lives | `AIPTP_DATA_DIR` (SQLite DB, encrypted keys, downloaded models, backups) |

## Updating

```bash
git pull
.venv/bin/pip install -e "backend[dev]"
cd frontend && npm install && npm run build && cd ..
```

Pre-1.0 there are no schema migrations: if the server fails to boot after
a big update, move/delete the data dir (`~/aiptp-data`) and start fresh
(it's simulated money — nothing of value is lost, though backups live in
`<data-dir>/backups` if you want the history).

## Sanity checks

```bash
curl http://localhost:8420/api/v1/health          # {"status":"ok",...}
cd backend && ../.venv/bin/python -m pytest -q    # full test suite
```
