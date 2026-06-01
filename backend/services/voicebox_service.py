import asyncio
import io
import os
import wave
import re
from typing import List, Tuple
import httpx
from bs4 import BeautifulSoup

MAX_SEGMENT_CHARS = 4800


def get_voicebox_base(url: str, port: int) -> str:
    url = url.rstrip("/")
    return f"{url}:{port}"


def extract_plain_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "ruby"]):
        # keep rt text (furigana) stripped but preserve main kanji text
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [ln.strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def _split_text(text: str) -> List[str]:
    """Split text into segments of at most MAX_SEGMENT_CHARS at paragraph/sentence boundaries."""
    paragraphs = re.split(r"\n{2,}", text)
    segments: List[str] = []
    current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(para) > MAX_SEGMENT_CHARS:
            # split long paragraph by sentence boundaries
            sentences = re.split(r"(?<=[。！？.!?])\s*", para)
            for sent in sentences:
                if not sent:
                    continue
                if len(current) + len(sent) + 1 > MAX_SEGMENT_CHARS:
                    if current:
                        segments.append(current.strip())
                    current = sent
                else:
                    current = (current + " " + sent).strip() if current else sent
        else:
            if len(current) + len(para) + 2 > MAX_SEGMENT_CHARS:
                if current:
                    segments.append(current.strip())
                current = para
            else:
                current = (current + "\n\n" + para).strip() if current else para

    if current.strip():
        segments.append(current.strip())

    return segments


def _concat_wav_bytes(wav_chunks: List[bytes]) -> bytes:
    """Concatenate multiple WAV byte blobs into a single WAV blob."""
    buf = io.BytesIO()
    out_wav = None
    for chunk in wav_chunks:
        with wave.open(io.BytesIO(chunk), "rb") as wf:
            params = wf.getparams()
            frames = wf.readframes(wf.getnframes())
        if out_wav is None:
            out_wav = wave.open(buf, "wb")
            out_wav.setparams(params)
        out_wav.writeframes(frames)
    if out_wav:
        out_wav.close()
    return buf.getvalue()


async def load_model(base_url: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{base_url}/models/load")
        resp.raise_for_status()
        return resp.json()


async def list_profiles(base_url: str) -> list:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{base_url}/profiles")
        resp.raise_for_status()
        return resp.json()


async def _wait_for_audio(
    client: httpx.AsyncClient,
    base_url: str,
    gen_id: str,
    poll_interval: float = 10.0,
    timeout: float = 600.0,
) -> dict:
    """Poll GET /history/{gen_id} until status is no longer 'generating'."""
    elapsed = 0.0
    while elapsed < timeout:
        resp = await client.get(f"{base_url}/history/{gen_id}")
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status", "")
        if status == "error":
            raise RuntimeError(f"Voicebox generation failed for id={gen_id}: {data.get('error')}")
        if status != "generating":
            return data
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval
    raise TimeoutError(f"Audio generation timed out after {timeout}s for id={gen_id}")


async def generate_chapter_audio(
    book_id: int,
    chapter_index: int,
    plain_text: str,
    profile_id: str,
    language: str,
    model_size: str,
    base_url: str,
    audio_dir: str,
) -> Tuple[str, float]:
    """Generate audio for a chapter, handling text > 4800 chars by splitting + concatenating."""
    segments = _split_text(plain_text)
    if not segments:
        raise ValueError("No text content to synthesize")

    wav_chunks: List[bytes] = []
    total_duration = 0.0

    async with httpx.AsyncClient(timeout=300) as client:
        for seg in segments:
            gen_resp = await client.post(
                f"{base_url}/generate",
                json={
                    "profile_id": profile_id,
                    "text": seg,
                    "language": language,
                    "model_size": model_size,
                },
            )
            gen_resp.raise_for_status()
            gen_id = gen_resp.json()["id"]

            history = await _wait_for_audio(client, base_url, gen_id)
            total_duration += float(history.get("duration", 0))

            audio_resp = await client.get(f"{base_url}/audio/{gen_id}")
            audio_resp.raise_for_status()
            wav_chunks.append(audio_resp.content)

            try:
                await client.delete(f"{base_url}/history/{gen_id}")
            except Exception:
                pass

    combined = _concat_wav_bytes(wav_chunks)

    out_dir = os.path.join(audio_dir, str(book_id))
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.abspath(os.path.join(out_dir, f"chapter_{chapter_index}.wav"))
    with open(out_path, "wb") as f:
        f.write(combined)

    return out_path, total_duration
