# ─────────────────────────────────────────────────────────────────────────────
#  ELAYA SMILES v2 — production image (CPU only)
#  Removed with respect to v1: dscribe/numba (unused), Auto3D (unused), aegon/glomos from PyPI
#  (GLOMOS now ships in ./elaya_glomos and is self-contained), flask-cors (replaced by 15 lines).
#  The local package is called elaya_glomos (not glomos) so that the unrelated `glomos` package on PyPI,
#  which v1 installed and which has no libreport.py, can never shadow it.
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

# Fail the build (not the first user request) if the GLOMOS package is incomplete or shadowed.
RUN pip uninstall -y glomos aegon >/dev/null 2>&1; \
    python -c "import elaya_glomos, elaya_glomos.libreport, elaya_glomos.libcalc_ani, elaya_glomos.libbatch, elaya_glomos.ani_domain, elaya_jobs; print('ELAYA GLOMOS package OK:', elaya_glomos.__file__)"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MALLOC_ARENA_MAX=2 \
    ELAYA_TORCH_THREADS=auto \
    ELAYA_MAX_JOBS=1 \
    ELAYA_MAX_MINUTES=20

EXPOSE 5000
# /api/health imports nothing heavy; ?deep=1 runs a real ANI calculation (use it manually after deploying)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:5000/api/health').status==200 else 1)"

CMD ["python", "app.py"]
