# -*- coding: utf-8 -*-
"""
Learning Scheduler – minimal MVP skeleton
========================================
A single‑file package ready to be imported from a Colab notebook.

Core responsibilities (phase‑1):
    • Persist a word database (JSON) with per‑word stats
    • Cache TTS audio for words (gTTS → mp3)
    • Provide two quiz modes: random() and wrong_only()
    • Expose simple CLI‑style helpers for Colab interaction

Designed so future extensions (SRS scheduling, STT, tags, dashboards, etc.)
can be added without breaking the public API.
"""

from __future__ import annotations

import json
import random
import uuid
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

try:
    from gtts import gTTS
    from IPython.display import Audio, display
except ImportError:  # Allow import outside Colab
    gTTS = None  # type: ignore
    Audio = None  # type: ignore
    display = print  # fallback

# ---------------------------------------------------------------------------
# Configuration – adjust BASE to your own Drive path if needed
# ---------------------------------------------------------------------------
BASE = Path("/content/drive/MyDrive/Projects/learning_scheduler")
DATA_DIR = BASE / "data"
WORDS_PATH = DATA_DIR / "words.json"
QUIZ_LOG_PATH = DATA_DIR / "quizzes.jsonl"
AUDIO_DIR_WORDS = DATA_DIR / "audio_cache" / "words_audio"
AUDIO_DIR_EXAMPLES = DATA_DIR / "audio_cache" / "examples_audio"

for p in [DATA_DIR, AUDIO_DIR_WORDS, AUDIO_DIR_EXAMPLES]:
    p.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Data‑layer helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path, default: Any) -> Any:
    if path.exists():
        with path.open("r", encoding="utf‑8") as f:
            return json.load(f)
    return default


def _save_json(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf‑8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class WordDB:
    """In‑memory wrapper around `words.json`."""

    def __init__(self) -> None:
        self.words: Dict[str, Dict[str, Any]] = _load_json(WORDS_PATH, {})

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def add_word(
        self,
        word: str,
        definition_en: str,
        examples: List[str] | None = None,
        ai_examples: List[str] | None = None,
    ) -> None:
        word = word.strip().lower()
        entry = self.words.get(word, {
            "word": word,
            "definition_en": definition_en,
            "examples": [],
            "ai_examples": [],
            "correct_cnt": 0,
            "wrong_cnt": 0,
            "created_at": datetime.utcnow().isoformat(),
        })
        entry["definition_en"] = definition_en  # allow update
        if examples:
            entry["examples"].extend(examples)
        if ai_examples:
            entry["ai_examples"].extend(ai_examples)
        self.words[word] = entry
        self._cache_word_audio(word)
        self.save()

    def increment_stat(self, word: str, correct: bool) -> None:
        entry = self.words[word]
        key = "correct_cnt" if correct else "wrong_cnt"
        entry[key] += 1
        self.save()

    # ------------------------------------------------------------------
    # I/O helpers
    # ------------------------------------------------------------------
    def save(self) -> None:
        _save_json(WORDS_PATH, self.words)

    # ------------------------------------------------------------------
    # Audio caching
    # ------------------------------------------------------------------
    def _cache_word_audio(self, word: str) -> None:
        if not gTTS:
            return  # running outside Colab
        mp3_path = AUDIO_DIR_WORDS / f"{word}.mp3"
        if not mp3_path.exists():
            tts = gTTS(text=word, lang="en")
            tts.save(str(mp3_path))

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------
    def weighted_sample(self, wrong_only: bool = False) -> str:
        items = [e for e in self.words.values() if (not wrong_only or e["wrong_cnt"] > 0)]
        assert items, "No words available for the requested mode."
        weights = [(w["wrong_cnt"] + 1) / (w["correct_cnt"] + 1) for w in items]
        return random.choices(items, weights=weights, k=1)[0]["word"]


WORD_DB = WordDB()

# ---------------------------------------------------------------------------
# TTS utilities (word + example)
# ---------------------------------------------------------------------------

def play_word(word: str, autoplay: bool = True):
    """Play cached pronunciation mp3."""
    mp3_path = AUDIO_DIR_WORDS / f"{word}.mp3"
    if Audio and mp3_path.exists():
        return display(Audio(str(mp3_path), autoplay=autoplay))


def play_example(text: str, autoplay: bool = True):
    if not gTTS or not Audio:
        return
    h = hashlib.md5(text.encode()).hexdigest()[:10]
    mp3_path = AUDIO_DIR_EXAMPLES / f"{h}.mp3"
    if not mp3_path.exists():
        gTTS(text=text, lang="en").save(str(mp3_path))
    return display(Audio(str(mp3_path), autoplay=autoplay))


# ---------------------------------------------------------------------------
# Quiz mechanics
# ---------------------------------------------------------------------------

def _make_choices(target_word: str, n_choices: int = 4) -> List[str]:
    words_pool = list(WORD_DB.words.keys())
    words_pool.remove(target_word)
    random.shuffle(words_pool)
    distractors = words_pool[: n_choices - 1]
    choices = [target_word] + distractors
    random.shuffle(choices)
    return choices


def _choice_label(idx: int) -> str:
    return ["A", "B", "C", "D", "E", "F"][idx]


def quiz_once(wrong_only: bool = False, reveal_answer: bool = True) -> bool:
    target = WORD_DB.weighted_sample(wrong_only=wrong_only)
    entry = WORD_DB.words[target]

    # Build option list of EN definitions
    options_words = _make_choices(target)
    options_defs = [WORD_DB.words[w]["definition_en"] for w in options_words]

    play_word(target)
    print(f"\n🔑  Definition of: **{target}**?\n")
    for i, defi in enumerate(options_defs):
        print(f"{_choice_label(i)}. {defi}")

    user = input("Your choice (A/B/C/D): ").strip().upper()
    correct = options_words[ _choice_label(["A","B","C","D"].index(user)) == "A" ] if False else None  # dummy line to keep linters quiet
    try:
        chosen = options_words[["A","B","C","D"].index(user)]
    except (ValueError, IndexError):
        print("Invalid input.")
        return False

    is_correct = chosen == target
    print("✅ Correct!" if is_correct else f"❌ Wrong. Answer was {target}")
    WORD_DB.increment_stat(target, is_correct)
    return is_correct


# ---------------------------------------------------------------------------
# Session‑level helpers
# ---------------------------------------------------------------------------

def quiz_session(n_questions: int = 20, wrong_only: bool = False):
    start = datetime.utcnow()
    correct = 0
    for _ in range(n_questions):
        if quiz_once(wrong_only=wrong_only):
            correct += 1
    accuracy = correct / n_questions * 100
    duration = (datetime.utcnow() - start).seconds

    log_entry = {
        "timestamp": start.isoformat(),
        "n_questions": n_questions,
        "correct": correct,
        "accuracy": accuracy,
        "mode": "wrong_only" if wrong_only else "random",
        "duration_sec": duration,
    }
    with QUIZ_LOG_PATH.open("a", encoding="utf‑8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    print(f"\n📊 Session complete: {correct}/{n_questions} correct ({accuracy:.1f}%) in {duration}s.")


# ---------------------------------------------------------------------------
# CLI shortcuts for Colab notebooks
# ---------------------------------------------------------------------------

def add(word: str, definition_en: str, examples: List[str] | None = None, ai_examples: List[str] | None = None):
    """Convenience wrapper used inside notebook.cell."""
    WORD_DB.add_word(word, definition_en, examples, ai_examples)
    print(f"Added/updated '{word}'.")


def show_words(limit: int = 20, order_by: str = "wrong"):
    sort_key = {
        "wrong": lambda e: -e[1]["wrong_cnt"],
        "recent": lambda e: e[1]["created_at"],
        "alpha": lambda e: e[0],
    }[order_by]
    items = sorted(WORD_DB.words.items(), key=sort_key)
    for i, (w, dat) in enumerate(items[:limit], 1):
        print(f"{i:>3}. {w:<15} wrong:{dat['wrong_cnt']:<3} correct:{dat['correct_cnt']:<3}")


if __name__ == "__main__":
    # Quick smoke test
    add("attention", "Focusing mechanism that assigns weights to inputs.")
    quiz_session(3)
