# -*- coding: utf-8 -*-
"""
Word‑Learning Scheduler (MVP v0.2.1)
====================================
Patch: • unify search/lookup naming  • single‑line output when searching

This file overwrites the previous v0.2 implementation.
"""
from __future__ import annotations

import json
import random
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from gtts import gTTS
from IPython.display import Audio, display

# ---------------------------------------------------------------------------
# Global config
# ---------------------------------------------------------------------------
BASE: Path = Path('.')  # to be overwritten by user
DATA_DIR: Path = None   # resolved inside setup_dirs()
AUDIO_DIR: Path = None
WORDS_PATH: Path = None
QUIZLOG_PATH: Path = None

WORDS_DB: Dict[str, dict] = {}

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def setup_dirs() -> None:
    """Create data & audio cache folders under BASE and load DB."""
    global DATA_DIR, AUDIO_DIR, WORDS_PATH, QUIZLOG_PATH

    DATA_DIR = BASE / 'data'
    AUDIO_DIR = DATA_DIR / 'audio_cache'
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (AUDIO_DIR / 'words_audio').mkdir(parents=True, exist_ok=True)
    (AUDIO_DIR / 'examples_audio').mkdir(parents=True, exist_ok=True)

    WORDS_PATH = DATA_DIR / 'words.json'
    QUIZLOG_PATH = DATA_DIR / 'quizzes.jsonl'
    load_db()

# ---------------------------------------------------------------------------
# DB IO
# ---------------------------------------------------------------------------

def load_db() -> None:
    global WORDS_DB
    if WORDS_PATH.exists():
        WORDS_DB = json.loads(WORDS_PATH.read_text())
    else:
        WORDS_DB = {}


def save_db() -> None:
    WORDS_PATH.write_text(json.dumps(WORDS_DB, ensure_ascii=False, indent=2))

# ---------------------------------------------------------------------------
# TTS helpers
# ---------------------------------------------------------------------------

def _word_mp3(word: str) -> Path:
    return AUDIO_DIR / 'words_audio' / f"{word.lower()}.mp3"


def _ensure_word_tts(word: str):
    mp3 = _word_mp3(word)
    if not mp3.exists():
        gTTS(word).save(mp3)
    return mp3


def _play_audio(mp3: Path):
    display(Audio(str(mp3), autoplay=True))

# ---------------------------------------------------------------------------
# Word operations
# ---------------------------------------------------------------------------

def add_word(word: str, *, definition_en: str, examples: Optional[List[str]] = None,
             tags: Optional[List[str]] = None):
    word = word.strip()
    ex_list = examples or []
    tag_list = tags or []

    record = WORDS_DB.get(word, {
        'definition_en': definition_en,
        'examples': ex_list,
        'tags': tag_list,
        'correct_cnt': 0,
        'wrong_cnt': 0,
        'added_at': _now_iso(),
    })

    # update definition/examples/tags if re‑adding
    record['definition_en'] = definition_en
    record['examples'] = ex_list
    record['tags'] = tag_list
    WORDS_DB[word] = record

    _ensure_word_tts(word)
    save_db()


# ---------------------------------------------------------------------------
# Search / lookup / edit / delete
# ---------------------------------------------------------------------------

def search_word(word: str, *, pretty: bool = True):
    """Return a word record; pretty print single layer if found."""
    entry = WORDS_DB.get(word)
    if entry and pretty:
        print({word: entry})
    elif not entry:
        print(f"'{word}' not found.")
    return entry

# alias for backward compatibility
find_word = lookup = search_word


def edit_word(word: str, **fields):
    if word not in WORDS_DB:
        print(f"'{word}' not found.")
        return
    WORDS_DB[word].update(fields)
    save_db()
    print(f"updated '{word}'.")


def delete_word(word: str):
    if word in WORDS_DB:
        WORDS_DB.pop(word)
        save_db()
        print(f"deleted '{word}'.")
    else:
        print(f"'{word}' not found.")

# ---------------------------------------------------------------------------
# Quiz helpers
# ---------------------------------------------------------------------------

def _weighted_sample(words: List[str], n: int, unique: bool = True) -> List[str]:
    if unique and len(words) >= n:
        population = random.sample(words, k=n)  # unique selection
        return population
    # fallback to weighted random with replacement
    weights = [WORDS_DB[w]['wrong_cnt'] + 1 for w in words]
    return random.choices(words, weights=weights, k=n)


def _multiple_choice(target: str, options: List[str]):
    print(f"\n👉 {target}")
    _play_audio(_word_mp3(target))
    for idx, opt in enumerate(options, 1):
        print(f"  {idx}. {opt}")
    ans = input("Your choice: ")
    return ans.strip()


# ---------------------------------------------------------------------------
# Public quiz APIs
# ---------------------------------------------------------------------------

def quiz_random(n: int = 5, *, unique: bool = True):
    words = list(WORDS_DB)
    if not words:
        print("No words in database.")
        return
    selected = _weighted_sample(words, n, unique=unique)
    _run_mc_quiz(selected)


def quiz_wrong(n: int = 5):
    wrong_words = [w for w, rec in WORDS_DB.items() if rec['wrong_cnt'] > 0]
    if not wrong_words:
        print("No wrong answers yet – great job!")
        return
    selected = _weighted_sample(wrong_words, n)
    _run_mc_quiz(selected)


def _run_mc_quiz(target_words: List[str]):
    correct = 0
    for tgt in target_words:
        # pick 3 distractors
        distractors = random.sample([w for w in WORDS_DB if w != tgt], k=min(3, len(WORDS_DB)-1))
        choices_defs = [WORDS_DB[w]['definition_en'] for w in distractors] + [WORDS_DB[tgt]['definition_en']]
        random.shuffle(choices_defs)
        user_ans = _multiple_choice(tgt, choices_defs)
        try:
            idx = int(user_ans) - 1
            is_correct = choices_defs[idx] == WORDS_DB[tgt]['definition_en']
        except Exception:
            is_correct = False
        print("✔️" if is_correct else "❌")
        _update_stats(tgt, is_correct)
        correct += is_correct
    print(f"\nQuiz done: {correct}/{len(target_words)} correct.")


def _update_stats(word: str, is_correct: bool):
    rec = WORDS_DB[word]
    rec['correct_cnt'] += int(is_correct)
    rec['wrong_cnt'] += int(not is_correct)
    save_db()

# ---------------------------------------------------------------------------
# Vocab & stats views
# ---------------------------------------------------------------------------

def show_vocab(order: str = 'wrong_desc'):
    rows = [(w, r['correct_cnt'] + r['wrong_cnt'], r['wrong_cnt']) for w, r in WORDS_DB.items()]
    if order == 'wrong_desc':
        rows.sort(key=lambda x: x[2], reverse=True)
    elif order == 'recent':
        rows.sort(key=lambda x: WORDS_DB[x[0]]['added_at'], reverse=True)
    print("word | attempts | wrong")
    for w, a, wr in rows:
        print(f"{w:20} {a:>3} {wr:>3}")


def show_stats():
    total = sum(r['correct_cnt'] + r['wrong_cnt'] for r in WORDS_DB.values())
    if not total:
        print("No quiz history yet.")
        return
    correct = sum(r['correct_cnt'] for r in WORDS_DB.values())
    print(f"Overall accuracy: {correct/total*100:.1f}%  (answered {total} questions)")

# end of file
