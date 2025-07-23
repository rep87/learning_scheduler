# Word_learning/utils.py
"""
utils.py
~~~~~~~~
• TTS 재생(speak)
• 문자열 거리(levenshtein)
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional

from . import core

# --------------------------------------------------------------
# 1. TTS (gTTS → MP3)  ----------------------------------------
# --------------------------------------------------------------

try:
    from gtts import gTTS
    from IPython.display import Audio, display
except ImportError:               # 노트북 런타임에 패키지가 없을 때
    gTTS = Audio = display = None


def _require_dirs() -> None:
    """core.setup_dirs() 가 안 돌았으면 자동 호출."""
    if core.AUDIO_DIR is None:
        core.setup_dirs()


def speak(word: str, *, lang: str = "en", autoplay: bool = True) -> None:
    """
    단어를 음성으로 읽어 줍니다.  
    gTTS 미설치·오프라인 환경이면 텍스트 안내만 출력합니다.
    """
    _require_dirs()

    if gTTS is None:
        print(f"[TTS unavailable] → {word}")
        return

    mp3: Path = core.AUDIO_DIR / f"{word.lower()}.mp3"
    if not mp3.exists():
        gTTS(word, lang=lang).save(str(mp3))
    display(Audio(str(mp3), autoplay=autoplay))


# --------------------------------------------------------------
# 2. Levenshtein ---------------------------------------------
# --------------------------------------------------------------
def levenshtein(a: str, b: str) -> int:
    """
    레벤슈타인 거리 O(len(a)·len(b))  
    외부 C 확장(python-Levenshtein)이 설치돼 있으면 그쪽으로 위임.
    """
    try:
        import Levenshtein as _lev  # type: ignore
        return _lev.distance(a, b)
    except ImportError:
        pass  # fallback to pure-python below

    if len(a) < len(b):
        a, b = b, a
    if len(b) == 0:
        return len(a)

    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            ins, dele, sub = (
                prev[j] + 1,
                curr[j - 1] + 1,
                prev[j - 1] + (ca != cb),
            )
            curr.append(min(ins, dele, sub))
        prev = curr
    return prev[-1]
