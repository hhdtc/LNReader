import os
import httpx
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

router = APIRouter(prefix="/api/tts", tags=["tts"])

TTS_BASE = os.getenv("TTS_URL_BASE", "http://lnreader-tts:8765")


class TTSRequest(BaseModel):
    text: str
    ref_audio_base64: str = ""  # ignored; ref audio is bundled in the TTS service


@router.post("")
async def synthesize(req: TTSRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{TTS_BASE}/tts", json={"text": req.text})

        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"TTS service error: {resp.text}")

        return resp.json()

    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="TTS service unavailable")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="TTS service timed out")


@router.post("/ref-audio")
async def upload_ref_audio(file: UploadFile = File(...)):
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{TTS_BASE}/ref-audio",
                files={"file": (file.filename, await file.read(), file.content_type)},
            )

        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"TTS service error: {resp.text}")

        return resp.json()

    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="TTS service unavailable")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="TTS service timed out")
