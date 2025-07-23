# word_learning/__init__.py
"""
Word-Learning Scheduler
=======================
Package init (v0.5.1-alpha)

공개 API를 한눈에 정리하고, BASE 경로 설정을 안전하게 처리합니다.
"""

from pathlib import Path
from types import ModuleType
from importlib import import_module

# ---- 하위 모듈 import ----
from . import core as _core
from .core import BASE, setup_dirs
from .vocab import (
    add_word, show_vocab, search_word,
    delete_word, edit_word
)
from .quiz import (
    quiz_random, quiz_spelling,
    show_sessions
)
from .utils import speak

__version__ = "0.5.1-alpha"

# 사용자가 import * 할 때 노출되는 심볼
__all__ = [
    "__version__",
    "setup_dirs", "set_base_path",
    # vocab
    "add_word", "show_vocab", "search_word",
    "delete_word", "edit_word",
    # quiz
    "quiz_random", "quiz_spelling", "show_sessions",
    # misc
    "speak",
]

# ------------------------------------------------------------
# 1. BASE 경로를 바꿀 수 있는 헬퍼
# ------------------------------------------------------------
def set_base_path(path) -> Path:
    """
    학습 데이터가 저장될 BASE 폴더를 바꿉니다.
    - path: str | pathlib.Path
    - 반환값: Path (새로운 BASE)
    동작:
      1) core.BASE 업데이트
      2) 디렉토리 구조 다시 생성 (setup_dirs)
      3) 성공한 BASE Path 를 리턴
    """
    new_base = Path(path).expanduser().resolve()
    _core.BASE = new_base
    setup_dirs()             # BASE 바뀌었으니 폴더 재설정
    return new_base

# ------------------------------------------------------------
# 2. 도움말
# ------------------------------------------------------------
def help():
    """패키지에서 바로 쓸 수 있는 주요 함수 목록을 보여줍니다."""
    print(
        "Word-Learning Scheduler – API\n"
        "=============================\n"
        "🗂  디렉토리 설정\n"
        "  • setup_dirs()        – BASE/data 폴더 생성\n"
        "  • set_base_path(path) – BASE 경로 변경 + 재설정\n\n"
        "📚  단어 관리\n"
        "  • add_word(word, definition, examples, tags)\n"
        "  • show_vocab(order='alpha'|'recent'|'wrong_desc')\n"
        "  • search_word(word) / edit_word(...) / delete_word(word)\n\n"
        "🎮  퀴즈\n"
        "  • quiz_random(n=10) / quiz_spelling(n=10)\n"
        "  • show_sessions(limit=10)\n\n"
        "🔈  기타\n"
        "  • speak(word) – TTS 재생\n"
    )
