# IndexTTS-2.5 TTS server — zero-shot voice cloning, ZH/EN/JA/ES/AR
# https://github.com/index-tts/index-tts
FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3.11 python3.11-dev python3.11-venv python3-pip \
        libsndfile1 ffmpeg wget git && \
    rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/python3.11 /usr/bin/python3 && \
    ln -sf /usr/bin/python3 /usr/bin/python

# uv is required by index-tts; the committed uv.lock pins exact versions
# (torch 2.8 + cu128 wheels, transformers, modelscope, ...)
RUN pip install --no-cache-dir uv

WORKDIR /app

RUN git clone --depth 1 https://github.com/index-tts/index-tts.git /app/index-tts && \
    cd /app/index-tts && uv sync

# FastAPI server deps (server.py), installed into the project venv
COPY requirements.txt /app/index-tts/requirements.txt
RUN cd /app/index-tts && uv pip install --python .venv/bin/python --no-cache-dir -r requirements.txt

COPY server.py /app/index-tts/server.py
COPY ref.wav /app/ref.wav

EXPOSE 8766

# Keep CWD=/app: infer_v2_5 resolves HF_HUB_CACHE as ./checkpoints/hf_cache
WORKDIR /app
CMD ["/app/index-tts/.venv/bin/python", "/app/index-tts/server.py"]
