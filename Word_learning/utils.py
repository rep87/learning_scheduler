# Word_learning/utils.py
"""
utils.py
~~~~~~~~
• TTS 재생(speak): 단어/문장 캐시 분리 + JS 재생 기본(위젯 생성 안 함)
• 문자열 거리(levenshtein)
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional
import hashlib
import re
import base64

from . import core

# --------------------------------------------------------------
# 1. TTS (gTTS → MP3)
# --------------------------------------------------------------
try:
    from gtts import gTTS
    from IPython.display import Audio, display, HTML, Javascript
except Exception:
    gTTS = None
    Audio = None
    display = None
    HTML = None
    Javascript = None


def _require_dirs() -> None:
    """core.setup_dirs() 가 안 돌았으면 자동 호출."""
    if core.AUDIO_WORD_DIR is None or core.AUDIO_SENT_DIR is None:
        core.setup_dirs()


def _is_sentence_text(text: str) -> bool:
    """공백(단어 2개 이상) 또는 문장부호가 있으면 문장으로 간주."""
    if len(text.split()) > 1:
        return True
    return bool(re.search(r"[.,;:!?]", text))


def _slug_word(text: str) -> str:
    """단어 파일명 안전화 (소문자, 영숫자/하이픈/언더스코어만)."""
    slug = re.sub(r"[^a-z0-9_-]+", "_", text.strip().lower())
    return slug or "word"


def _norm_sentence(text: str) -> str:
    """문장 해시용 정규화: 공백 정리 + 트림."""
    return re.sub(r"\s+", " ", text.strip())


def _tts_cache_path(text: str, is_sentence: bool) -> Path:
    """문장/단어에 맞는 캐시 경로 반환."""
    _require_dirs()
    if is_sentence:
        norm = _norm_sentence(text)
        h = hashlib.sha1(norm.encode("utf-8")).hexdigest()[:16]
        return core.AUDIO_SENT_DIR / f"sent_{h}.mp3"  # type: ignore[arg-type]
    else:
        return core.AUDIO_WORD_DIR / f"{_slug_word(text)}.mp3"  # type: ignore[arg-type]


def speak(
    text: str,
    *,
    lang: str = "en",
    autoplay: bool = True,
    slow: bool = False,
    force_sentence: Optional[bool] = None,
    ui: str = "js",
) -> None:
    """
    텍스트를 음성으로 재생(캐시 사용).
    - 문장: data/audio_cache/sentences_audio/sent_<sha1>.mp3
    - 단어: data/audio_cache/words_audio/<slug>.mp3

    ui:
      - "js"     : DOM 위젯 없이 JS로 재생(권장, input() 겹침 방지)
      - "hidden" : <audio>를 0px로 숨겨 임베드
      - "player" : 플레이어 노출(디버그용)

    gTTS/Audio 미설치·오프라인이면 텍스트 안내만 출력.
    """
    _require_dirs()

    is_sentence = force_sentence if force_sentence is not None else _is_sentence_text(text)
    mp3: Path = _tts_cache_path(text, is_sentence)

    if gTTS is None:
        print(f"[TTS unavailable] → {text}\n(cache: {mp3})")
        return

    if not mp3.exists():
        try:
            payload = _norm_sentence(text) if is_sentence else text
            gTTS(payload, lang=lang, slow=slow).save(str(mp3))
        except Exception as e:
            print(f"[TTS failed] {e} → {text}")
            return

    # ── 재생 ──────────────────────────────────────────────────
    try:
        if ui == "player" and Audio is not None and display is not None:
            display(Audio(str(mp3), autoplay=autoplay))
            return

        if ui == "hidden" and Audio is not None and display is not None and HTML is not None:
            ao = Audio(str(mp3), autoplay=autoplay)
            hidden = '<div style="height:0;overflow:hidden">' + ao._repr_html_() + "</div>"
            display(HTML(hidden))
            return

        # ui == "js" (default): mp3 바이트를 data URI로 JS 재생 → 위젯 없음, 레이아웃 이동 없음
        if ui == "js" and Javascript is not None and display is not None:
            b64 = base64.b64encode(mp3.read_bytes()).decode("ascii")
            data_uri = "data:audio/mpeg;base64," + b64
            autoplay_js = "true" if autoplay else "false"
            js_lines = [
                "(function(){",
                "  try {",
                f'    var a = new Audio("{data_uri}");',
                f"    a.autoplay = {autoplay_js};",
                "    a.play().catch(function(){});",
                "  } catch(e) {}",
                "})();",
            ]
            display(Javascript("\n".join(js_lines)))
            return

        # JS 미가용 시 최소한의 숨김 임베드
        if Audio is not None and display is not None and HTML is not None:
            ao = Audio(str(mp3), autoplay=autoplay)
            hidden = '<div style="height:0;overflow:hidden">' + ao._repr_html_() + "</div>"
            display(HTML(hidden))
        else:
            print(f"[Audio playback not available] (cached at: {mp3})")

    except Exception as e:
        print(f"[Audio playback failed] {e} → {text} (cached at: {mp3})")


# --------------------------------------------------------------
# 2. Levenshtein
# --------------------------------------------------------------
def levenshtein(a: str, b: str) -> int:
    """
    레벤슈타인 거리 O(len(a)·len(b))
    외부 C 확장(python-Levenshtein)이 설치돼 있으면 그쪽으로 위임.
    """
    try:
        import Levenshtein as _lev  # type: ignore
        return _lev.distance(a, b)
    except Exception:
        pass  # fallback to pure-python below

    if len(a) < len(b):
        a, b = b, a
    if len(b) == 0:
        return len(a)

    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            ins = prev[j] + 1
            dele = curr[j - 1] + 1
            sub = prev[j - 1] + (ca != cb)
            curr.append(min(ins, dele, sub))
        prev = curr
    return prev[-1]
