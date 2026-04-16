import re
import unicodedata
from typing import List, Tuple

import fugashi
import jaconv


HIRAGANA_RANGE = (0x3041, 0x3096)
KATAKANA_RANGE = (0x30A0, 0x30FF)
KANJI_RANGE = (0x4E00, 0x9FFF)
CJK_EXTENSION_A = (0x3400, 0x4DBF)
FULLWIDTH_RANGE = (0xFF01, 0xFF60)

_tagger = fugashi.Tagger()


def is_japanese_char(char: str) -> bool:
    code = ord(char)
    return (
        HIRAGANA_RANGE[0] <= code <= HIRAGANA_RANGE[1]
        or KATAKANA_RANGE[0] <= code <= KATAKANA_RANGE[1]
        or KANJI_RANGE[0] <= code <= KANJI_RANGE[1]
        or CJK_EXTENSION_A[0] <= code <= CJK_EXTENSION_A[1]
    )


def _contains_kanji(text: str) -> bool:
    for ch in text:
        code = ord(ch)
        if (KANJI_RANGE[0] <= code <= KANJI_RANGE[1] or
                CJK_EXTENSION_A[0] <= code <= CJK_EXTENSION_A[1]):
            return True
    return False


def _wrap_chars_in_spans(text: str) -> str:
    result = []
    for char in text:
        code = ord(char)
        if HIRAGANA_RANGE[0] <= code <= HIRAGANA_RANGE[1]:
            result.append(f'<span class="hiragana">{char}</span>')
        elif KATAKANA_RANGE[0] <= code <= KATAKANA_RANGE[1]:
            result.append(f'<span class="katakana">{char}</span>')
        elif (KANJI_RANGE[0] <= code <= KANJI_RANGE[1] or
              CJK_EXTENSION_A[0] <= code <= CJK_EXTENSION_A[1]):
            result.append(f'<span class="kanji">{char}</span>')
        else:
            result.append(char)
    return "".join(result)


def detect_language(text: str) -> str:
    """Simple language detection based on character frequency."""
    if not text:
        return "unknown"
    sample = text[:2000]
    jp_count = sum(1 for c in sample if is_japanese_char(c))
    ratio = jp_count / max(len(sample), 1)
    if ratio > 0.05:
        return "ja"
    return "unknown"


def annotate_japanese(text: str) -> str:
    """
    Annotate Japanese text with:
    - <ruby> tags with hiragana readings for kanji words
    - Color-coded <span> tags for hiragana, katakana, and kanji characters
    """
    tokens = _tagger(text)
    result = []

    for token in tokens:
        surface = token.surface
        if not surface:
            continue

        if _contains_kanji(surface):
            reading_raw = getattr(token.feature, 'kana', None)
            reading = jaconv.kata2hira(reading_raw) if reading_raw else None

            if reading and reading != surface:
                inner = _wrap_chars_in_spans(surface)
                result.append(f'<ruby>{inner}<rt>{reading}</rt></ruby>')
            else:
                result.append(_wrap_chars_in_spans(surface))
        else:
            result.append(_wrap_chars_in_spans(surface))

    return "".join(result)
