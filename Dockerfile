# ─────────────────────────────────────────────────────────────────────────────
#  ELAYA SMILES — Production Dockerfile for Render
#  Uses Python 3.10-slim and CPU-only PyTorch to keep the image under ~2 GB.
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.10-slim

# ── System dependencies ───────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    wget \
    libgl1 \
    libglib2.0-0 \
    libxrender1 \
    libxext6 \
    libsm6 \
    libboost-all-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Copy project files ────────────────────────────────────────────────────────
COPY . .

# ── Upgrade pip ───────────────────────────────────────────────────────────────
RUN pip install --upgrade pip --no-cache-dir

# ── Step 1: CPU-only PyTorch (must be installed BEFORE torchani / Auto3D) ────
#    The +cpu index avoids downloading the 2.5 GB CUDA wheel.
RUN pip install --no-cache-dir \
    torch==2.2.2+cpu \
    --index-url https://download.pytorch.org/whl/cpu

# ── Step 2: TorchANI (depends on torch) ──────────────────────────────────────
RUN pip install --no-cache-dir torchani

# ── Step 3: Core science stack ────────────────────────────────────────────────
#    numpy must be <2 — torch 2.2.x, dscribe, and ase were all compiled against
#    numpy 1.x ABI. numpy 2.x breaks them at import time.
RUN pip install --no-cache-dir "numpy<2" scipy networkx ase dscribe

# ── Step 4: Cheminformatics ───────────────────────────────────────────────────
RUN pip install --no-cache-dir \
    rdkit \
    openbabel-wheel \
    py3Dmol

# ── Step 5: Auto3D (AI-based conformer generation) ───────────────────────────
#    --no-deps prevents Auto3D from re-installing a CUDA torch on top of our CPU one.
#    psutil is a direct import in auto3D.py but not declared in its setup.py.
#    send2trash is required by Auto3D's isomer_engine but omitted when using --no-deps.
RUN pip install --no-cache-dir "auto3d==2.3.1" --no-deps && \
    pip install --no-cache-dir psutil biopython geometric send2trash || true

# ── Step 6: GLOMOS (genetic algorithm for rotamers) ──────────────────────────
#    Install from PyPI if available, otherwise from local package directory.
RUN pip install --no-cache-dir glomos || \
    ([ -d "/app/glomos" ] && pip install --no-cache-dir /app/glomos) || \
    echo "WARNING: glomos not found on PyPI or local path — GLOMOS features will be unavailable"

# ── Step 7: Web server ────────────────────────────────────────────────────────
RUN pip install --no-cache-dir \
    flask \
    flask-cors \
    waitress

# ── Runtime environment ───────────────────────────────────────────────────────
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
# Prevents OpenBabel from looking for data files in Windows-style paths
ENV BABEL_DATADIR=/usr/local/lib/python3.10/site-packages/openbabel

EXPOSE 5000

# ── Healthcheck ───────────────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD wget -qO- http://localhost:5000/api || exit 1

CMD ["python", "app.py"]
