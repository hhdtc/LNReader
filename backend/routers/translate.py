import httpx
from fastapi import APIRouter, HTTPException
from schemas import TranslationRequest, TranslationResponse

router = APIRouter(prefix="/api/translate", tags=["translate"])


@router.post("", response_model=TranslationResponse)
async def translate_text(body: TranslationRequest):
    if not body.api_key:
        raise HTTPException(status_code=400, detail="API key is required")
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    provider = body.provider.lower()

    try:
        if provider == "deepl":
            return await _translate_deepl(body)
        elif provider == "google":
            return await _translate_google(body)
        elif provider == "openai":
            return await _translate_openai(body)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Translation error: {str(e)}")


async def _translate_deepl(body: TranslationRequest) -> TranslationResponse:
    # DeepL Free API uses api-free.deepl.com; Pro uses api.deepl.com
    # We auto-detect based on key suffix ":fx"
    base = "https://api-free.deepl.com" if body.api_key.endswith(":fx") else "https://api.deepl.com"
    url = f"{base}/v2/translate"

    target = body.target_lang.upper()
    if target == "EN":
        target = "EN-US"

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            headers={"Authorization": f"DeepL-Auth-Key {body.api_key}"},
            json={
                "text": [body.text],
                "source_lang": body.source_lang.upper(),
                "target_lang": target,
            }
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=f"DeepL error: {resp.text}")
    data = resp.json()
    return TranslationResponse(
        translated_text=data["translations"][0]["text"],
        provider="deepl"
    )


async def _translate_google(body: TranslationRequest) -> TranslationResponse:
    url = "https://translation.googleapis.com/language/translate/v2"
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, params={"key": body.api_key}, json={
            "q": body.text,
            "source": body.source_lang,
            "target": body.target_lang,
            "format": "text"
        })
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=f"Google Translate error: {resp.text}")
    data = resp.json()
    translated = data["data"]["translations"][0]["translatedText"]
    return TranslationResponse(translated_text=translated, provider="google")


async def _translate_openai(body: TranslationRequest) -> TranslationResponse:
    LANG_NAMES = {"ja": "Japanese", "en": "English", "zh": "Chinese", "ko": "Korean"}
    src = LANG_NAMES.get(body.source_lang, body.source_lang)
    tgt = LANG_NAMES.get(body.target_lang, body.target_lang)

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {body.api_key}"},
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": f"You are a translation assistant. Translate the following text from {src} to {tgt}. Return only the translated text with no additional explanation."},
                    {"role": "user", "content": body.text}
                ],
                "temperature": 0.1,
            },
            timeout=30.0
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=f"OpenAI error: {resp.text}")
    data = resp.json()
    return TranslationResponse(
        translated_text=data["choices"][0]["message"]["content"],
        provider="openai"
    )
