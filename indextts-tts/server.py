import base64
import io
import logging
import os
import shutil
from contextlib import asynccontextmanager

import soundfile as sf
from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

REF_AUDIO_DEFAULT = "/app/ref.wav"
REF_AUDIO_CUSTOM = "/app/data/ref.wav"

MODEL_REPO = os.getenv("INDEXTTS_MODEL_REPO", "IndexTeam/IndexTTS-2.5")
MODEL_DIR = os.getenv("INDEXTTS_MODEL_DIR", "/app/checkpoints")
DEVICE = os.getenv("INDEXTTS_DEVICE", "cuda:0")
LANG = os.getenv("INDEXTTS_LANG", "JA").upper()
USE_BF16 = os.getenv("INDEXTTS_BF16", "1").lower() in ("1", "true", "yes")
SAMPLE_RATE = 22050  # IndexTTS-2.5 native output rate

SUPPORTED_LANGS = {"ZH", "EN", "JA", "ES", "AR"}

model = None


def get_ref_audio() -> str:
    if os.path.exists(REF_AUDIO_CUSTOM):
        return REF_AUDIO_CUSTOM
    return REF_AUDIO_DEFAULT


def ensure_model_files() -> None:
    """Download the main IndexTTS-2.5 repo and aux models into MODEL_DIR if missing."""
    config_path = os.path.join(MODEL_DIR, "config.yaml")
    if not os.path.isfile(config_path):
        log.info("Downloading %s to %s ...", MODEL_REPO, MODEL_DIR)
        os.makedirs(MODEL_DIR, exist_ok=True)
        from indextts.utils.model_download import snapshot_download
        snapshot_download(MODEL_REPO, local_dir=MODEL_DIR)
    from indextts.utils.model_download import ensure_models_available
    ensure_models_available(MODEL_DIR)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global model
    os.makedirs("/app/data", exist_ok=True)
    from indextts.infer_v2_5 import IndexTTS2
    ensure_model_files()
    log.info("Loading IndexTTS-2.5 from %s on %s (bf16=%s) ...", MODEL_DIR, DEVICE, USE_BF16)
    model = IndexTTS2(
        cfg_path=os.path.join(MODEL_DIR, "config.yaml"),
        model_dir=MODEL_DIR,
        use_bf16=USE_BF16,
        device=DEVICE,
    )
    log.info("Model ready. Ref audio: %s | lang: %s", get_ref_audio(), LANG)
    yield
    model = None


app = FastAPI(lifespan=lifespan)


class TTSRequest(BaseModel):
    text: str
    lang: str = LANG
    language: str = ""  # optional alias for lang (zh/en/ja); takes precedence when set
    duration_factor: float = 1.0


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model": "IndexTTS-2.5",
        "model_loaded": model is not None,
        "ref_audio": get_ref_audio(),
        "lang": LANG,
        "sample_rate": SAMPLE_RATE,
    }


@app.post("/tts")
async def tts(req: TTSRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="text is empty")
    if model is None:
        raise HTTPException(status_code=503, detail="model not loaded")

    lang = (req.language or req.lang).strip().upper()
    if lang not in SUPPORTED_LANGS:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported lang {lang!r}; expected one of {sorted(SUPPORTED_LANGS)}",
        )

    out_path = "/tmp/indextts_out.wav"
    try:
        result = model.infer(
            spk_audio_prompt=get_ref_audio(),
            text=req.text,
            lang=lang,
            output_path=out_path,
            duration_factor=req.duration_factor,
            verbose=False,
        )
        if result is None:
            raise HTTPException(status_code=500, detail="generation produced no audio")
    except HTTPException:
        raise
    except Exception as e:
        log.exception("IndexTTS-2.5 generation failed")
        raise HTTPException(status_code=500, detail=str(e))

    try:
        data, sr = sf.read(out_path, dtype="float32")
        buf = io.BytesIO()
        sf.write(buf, data, sr, format="WAV")
        audio_b64 = base64.b64encode(buf.getvalue()).decode()
    finally:
        if os.path.exists(out_path):
            os.remove(out_path)
    return {"audio_base64": audio_b64}


@app.post("/ref-audio")
async def upload_ref_audio(file: UploadFile = File(...)):
    os.makedirs("/app/data", exist_ok=True)
    try:
        with open(REF_AUDIO_CUSTOM, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        log.exception("Failed to save ref audio")
        raise HTTPException(status_code=500, detail=str(e))
    log.info("Ref audio updated: %s", REF_AUDIO_CUSTOM)
    return {"status": "ok", "ref_audio": REF_AUDIO_CUSTOM}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("INDEXTTS_PORT", "8766")))
