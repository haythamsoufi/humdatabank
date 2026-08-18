FROM python:3.12-slim

WORKDIR /app

# libgomp1: CTranslate2's Linux wheels link against OpenMP at runtime; it is
# not present in the slim base image and its absence fails at import time,
# not at build time.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# CPU-only PyTorch wheel, installed separately (own layer, own index) so a
# plain `pip install -r requirements.txt` elsewhere never pulls the much
# larger CUDA-enabled build. Only needed once, to load the original Hugging
# Face weights during the first model conversion (see app.py::_load_model).
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# Model cache (downloaded HF weights + converted CTranslate2 model). Mount a
# named volume here in docker-compose.yml so restarts skip the multi-minute
# download/conversion step.
RUN mkdir -p /models
ENV NLLB_CACHE_DIR=/models

EXPOSE 9100

# start-period is long because the very first boot downloads + converts a
# ~1.3B-parameter model (10-30+ minutes depending on bandwidth/CPU); once the
# converted model is cached in the mounted volume, subsequent boots are fast
# and /health flips to ok=true within seconds.
HEALTHCHECK --interval=30s --timeout=10s --start-period=45m --retries=3 \
    CMD python -c "import json,urllib.request,sys; sys.exit(0 if json.loads(urllib.request.urlopen('http://127.0.0.1:9100/health', timeout=8).read()).get('ok') else 1)" || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9100"]
