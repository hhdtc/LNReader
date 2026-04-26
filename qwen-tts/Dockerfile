FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/licyk/qwen-tts-webui .

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 7860

CMD ["python", "launch.py", "--api", "--server-name", "0.0.0.0", "--server-port", "7860"]
