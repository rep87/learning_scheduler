# Word_learning/utils.py

from .core import AUDIO_DIR

try:
    from gtts import gTTS
    from IPython.display import Audio, display
except ImportError:
    gTTS, Audio, display = None, None, None

def speak(word: str):
    """gTTS를 사용하여 단어를 소리내어 읽어줍니다."""
    if gTTS is None:
        print("[TTS unavailable: Please run 'pip install gtts']\n")
        return
    # setup_dirs()가 먼저 호출되어 AUDIO_DIR이 설정되었다고 가정
    mp3 = AUDIO_DIR / f"{word.lower()}.mp3"
    if not mp3.exists():
        gTTS(word).save(str(mp3))
    display(Audio(str(mp3), autoplay=True))

def levenshtein(a: str, b: str) -> int:
    """두 문자열 간의 레벤슈타인 거리를 계산합니다."""
    if len(a) < len(b): a, b = b, a
    if len(b) == 0: return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            ins, dele, sub = prev[j] + 1, curr[j-1] + 1, prev[j-1] + (ca != cb)
            curr.append(min(ins, dele, sub))
        prev = curr
    return prev[-1]
