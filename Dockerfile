# ─────────────────────────────────────────────────────────────────────────────
#  ELAYA SMILES v2 — production image (CPU only)
#  Removed with respect to v1: dscribe/numba (unused), Auto3D (unused), aegon/glomos from PyPI
#  (GLOMOS now ships in ./glomos and is self-contained), flask-cors (replaced by 15 lines).
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 libxrender1 libxext6 libsm6 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir torch==2.2.2 --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements.txt

# torchani 2.2.4 ships EMPTY placeholder parameter files and downloads the real ones from GitHub
# the first time a model is built. Doing that inside the first GLOMOS job (and again after every
# container restart) costs time and memory and fails if GitHub is unreachable. Download them now;
# the build fails here, loudly, if they cannot be obtained.
RUN python -W ignore -c "import torchani; [getattr(torchani.models, m)() for m in ('ANI1x', 'ANI1ccx', 'ANI2x')]; print('ANI parameters installed')"

COPY . .

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OMP_NUM_THREADS=2 \
    ELAYA_TORCH_THREADS=2 \
    ELAYA_MAX_JOBS=1 \
    ELAYA_MAX_MINUTES=20

EXPOSE 5000
# /api/health imports nothing heavy; ?deep=1 runs a real ANI calculation (use it manually after deploying)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:5000/api/health').status==200 else 1)"

CMD ["python", "app.py"]
