import io
import base64
import logging
import os
import shutil
from contextlib import asynccontextmanager

import numpy as np
import soundfile as sf
import torch
from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

REF_AUDIO_DEFAULT = "/app/ref.wav"
REF_AUDIO_CUSTOM = "/app/data/ref.wav"
MODEL_ID = os.getenv("OMNIVOICE_MODEL", "k2-fsa/OmniVoice")
DEVICE = os.getenv("OMNIVOICE_DEVICE", "cuda:0")
DTYPE = torch.float16

model = None


def get_ref_audio() -> str:
    if os.path.exists(REF_AUDIO_CUSTOM):
        return REF_AUDIO_CUSTOM
    return REF_AUDIO_DEFAULT


@asynccontextmanager
async def lifespan(app: FastAPI):
    global model
    os.makedirs("/app/data", exist_ok=True)
    from omnivoice import OmniVoice
    log.info("Loading OmniVoice model %s on %s ...", MODEL_ID, DEVICE)
    model = OmniVoice.from_pretrained(MODEL_ID, device_map=DEVICE, dtype=DTYPE)
    log.info("Model ready. Using ref audio: %s", get_ref_audio())
    yield
    model = None


app = FastAPI(lifespan=lifespan)


class TTSRequest(BaseModel):
    text: str


@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": model is not None, "ref_audio": get_ref_audio()}


@app.post("/tts")
async def tts(req: TTSRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="text is empty")
    if model is None:
        raise HTTPException(status_code=503, detail="model not loaded")

    try:
        audio_list = model.generate(
            text=req.text,
            ref_audio=get_ref_audio(),
        )
    except Exception as e:
        log.exception("OmniVoice generation failed")
        raise HTTPException(status_code=500, detail=str(e))

    audio: np.ndarray = audio_list[0]
    buf = io.BytesIO()
    sf.write(buf, audio, samplerate=24000, format="WAV")
    audio_b64 = base64.b64encode(buf.getvalue()).decode()
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
