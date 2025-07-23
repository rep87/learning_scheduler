# word_learning/__init__.py

"""
Word‑Learning Scheduler (v0.5.0-refactor)
========================================
Refactored for modularity and maintainability.
"""

# 사용자에게 노출할 주요 함수들을 각 모듈에서 가져옵니다.
from .core import BASE, setup_dirs
from .vocab import add_word, show_vocab, search_word, delete_word, edit_word
from .quiz import quiz_random, quiz_spelling, show_sessions
from .utils import speak

# 전역 변수 BASE를 외부에서 수정할 수 있도록 허용
def set_base_path(path):
    global BASE
    from pathlib import Path
    # core 모듈의 BASE 변수를 직접 수정합니다.
    globals()['core'].BASE = Path(path)

def help():
    print("Available functions:\n"
          " setup_dirs()\n"
          " add_word(word, definition_en, examples, tags)\n"
          " search_word(word) / edit_word / delete_word\n"
          " show_vocab(order)\n\n"
          " Quizzes:\n"
          "  quiz_random(n), quiz_spelling(n)\n"
          "  show_sessions(limit)\n"
          "  speak(word)")
