import os
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/tts", tags=["tts"])


class TTSRequest(BaseModel):
    text: str
    ref_audio_base64: str


@router.post("")
async def synthesize(req: TTSRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    tts_url = os.getenv("TTS_URL", "http://jpreader-tts:7860/qwenapi/v1/voice-clone")
    model_name = os.getenv("TTS_MODEL", "/models/Qwen3-TTS-12Hz-1.7B-Base")

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(tts_url, json={
                "model_name": model_name,
                "text": req.text,
                "ref_audio_base64": req.ref_audio_base64,
                "language": None,
                "segment_gen": False,
            })

        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"TTS service error: {resp.text}")

        result = resp.json()
        audio_files = result.get("audio_files_base64", [])
        if not audio_files:
            raise HTTPException(status_code=502, detail="TTS service returned no audio")

        return {"audio_base64": audio_files[0]}

    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="TTS service unavailable")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="TTS service timed out")
