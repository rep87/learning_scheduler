# -*- coding: utf-8 -*-
"""
Word‑Learning Scheduler  (v0.3.1)
=================================
• Persists a word DB with stats & tags → words.json
• Caches *only word‑level* TTS audio (gTTS) under words_audio/
• Example sentences are *not* cached; they are spoken on‑demand and discarded
• Quiz modes: multiple‑choice, wrong‑only, recall(type‑in)
• Per‑session quiz logs → quizzes.jsonl  (view with show_sessions)

Todo bucket (future work): see README or project discussion – SRS, STT, web import, etc.
"""
from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from gtts import gTTS
from IPython.display import Audio, display

# Public module alias will be set by loader (word_learning_scheduler)

# ---------------------------------------------------------------------------
# Global configuration
# ---------------------------------------------------------------------------
BASE: Path = Path('.')  # user should overwrite before first use
DATA_DIR: Path = Path('.')  # will be BASE / 'data'
AUDIO_WORDS_DIR: Path = Path('.')  # BASE / data / audio_cache / words_audio

VERSION = '0.3.1'

# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def setup_dirs() -> None:
    """Create BASE/data directories and bind globals."""
    global DATA_DIR, AUDIO_WORDS_DIR
    DATA_DIR = BASE / 'data'
    AUDIO_WORDS_DIR = DATA_DIR / 'audio_cache' / 'words_audio'

    AUDIO_WORDS_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / 'audio_cache').mkdir(parents=True, exist_ok=True)

    # Create empty JSON/JSONL if not exist
    (DATA_DIR / 'words.json').write_text('{}', encoding='utf-8') if not (DATA_DIR / 'words.json').exists() else None
    (DATA_DIR / 'quizzes.jsonl').touch()  # keep as empty file if new


def _words_path() -> Path:
    return DATA_DIR / 'words.json'


def load_db() -> Dict[str, dict]:
    return json.loads(_words_path().read_text(encoding='utf-8'))


def save_db(db: Dict[str, dict]) -> None:
    _words_path().write_text(json.dumps(db, ensure_ascii=False, indent=2))

# ---------------------------------------------------------------------------
# TTS utilities
# ---------------------------------------------------------------------------

def _word_audio_path(word: str) -> Path:
    return AUDIO_WORDS_DIR / f"{word.lower()}.mp3"


def _speak(text: str, cache_path: Optional[Path] = None):
    """Play `text` – cache if path provided, else temp playback only."""
    if cache_path is not None and cache_path.exists():
        display(Audio(str(cache_path), autoplay=True))
        return
    # synthesize
    tts = gTTS(text)
    path = cache_path if cache_path is not None else Path('/tmp') / f"tmp_{int(time.time()*1000)}.mp3"
    tts.save(str(path))
    display(Audio(str(path), autoplay=True))
    # delete temp file if not cached
    if cache_path is None:
        path.unlink(missing_ok=True)

# ---------------------------------------------------------------------------
# Core public API
# ---------------------------------------------------------------------------

def add_word(word: str, definition_en: str, examples: Optional[List[str]] = None, tags: Optional[List[str]] = None) -> None:
    db = load_db()
    entry = db.get(word, {
        'definition_en': definition_en,
        'examples': examples or [],
        'tags': tags or [],
        'correct_cnt': 0,
        'wrong_cnt': 0,
        'added_at': _now_iso()
    })
    # update fields
    entry['definition_en'] = definition_en
    if examples:
        entry['examples'] = examples
    if tags:
        entry['tags'] = tags
    db[word] = entry
    save_db(db)

    # cache & play word audio
    _speak(word, _word_audio_path(word))


def search_word(word: str, display_info: bool = True):
    db = load_db()
    if word not in db:
        print(f"❌ '{word}' not found")
        return None
    info = db[word]
    if display_info:
        print(f"{word}")
        for k, v in info.items():
            print(f"  ├ {k:<12}: {v}")
    return info

# alias for compatibility
find_word = search_word

# ---------------------------------------------------------------------------
# Example speech on‑demand (not cached)
# ---------------------------------------------------------------------------

def speak_example(word: str, idx: int = 0):
    """Speak the idx‑th example sentence for `word` without caching."""
    info = search_word(word, display_info=False)
    if not info:
        return
    examples = info.get('examples', [])
    if not examples:
        print("(no examples saved)")
        return
    if idx >= len(examples):
        print(f"Only {len(examples)} example(s) available.")
        return
    sentence = examples[idx]
    print("EXAMPLE:", sentence)
    _speak(sentence)  # temp playback only

# ---------------------------------------------------------------------------
# Quiz logic (simplified, unchanged)
# ---------------------------------------------------------------------------

def _sample_words(n: int, wrong_only: bool = False) -> List[str]:
    db = load_db()
    pool = [w for w, d in db.items() if (d['wrong_cnt'] > 0) or not wrong_only]
    if len(pool) == 0:
        print("No words available for quiz.")
        return []
    if n > len(pool):
        random.shuffle(pool)
        return pool  # allow smaller set
    return random.sample(pool, n)


def _log_session(mode: str, total: int, correct: int, started_at: float):
    acc = round((correct / total) * 100) if total else 0
    record = {
        'mode': mode,
        'total': total,
        'correct': correct,
        'acc': acc,
        'started_at': datetime.utcfromtimestamp(started_at).isoformat(),
        'duration_sec': int(time.time() - started_at)
    }
    with (_session_path := DATA_DIR / 'quizzes.jsonl').open('a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')


def quiz_random(n: int = 10):
    _quiz_core(n, mode='Random')


def quiz_wrong(n: int = 10):
    _quiz_core(n, mode='WrongOnly', wrong_only=True)


def _quiz_core(n: int, mode: str, wrong_only: bool = False):
    words = _sample_words(n, wrong_only=wrong_only)
    if not words:
        return
    db = load_db()
    correct = 0
    start_t = time.time()
    for word in words:
        entry = db[word]
        defs = [entry['definition_en']]
        # pick 3 random other definitions
        other_defs = [d['definition_en'] for w, d in db.items() if w != word]
        defs.extend(random.sample(other_defs, k=min(3, len(other_defs))))
        random.shuffle(defs)

        print(f"\n▶ What is the definition of '{word}'?")
        _speak(word, _word_audio_path(word))
        for i, d in enumerate(defs, 1):
            print(f"  {i}. {d}")
        ans = input("Your choice (1‑4): ")
        try:
            idx = int(ans) - 1
        except ValueError:
            idx = -1
        if idx >= 0 and idx < len(defs) and defs[idx] == entry['definition_en']:
            print("✔ Correct!\n")
            entry['correct_cnt'] += 1
            correct += 1
        else:
            print(f"✘ Wrong. → {entry['definition_en']}\n")
            entry['wrong_cnt'] += 1
    save_db(db)
    acc = round((correct / len(words)) * 100)
    print(f"\n=== Result: {correct}/{len(words)} correct | {acc}% ===")
    _log_session(mode, len(words), correct, start_t)

# ---------------------------------------------------------------------------
# Session viewer
# ---------------------------------------------------------------------------

def show_sessions(limit: int = 10):
    path = DATA_DIR / 'quizzes.jsonl'
    if not path.exists():
        print("(no sessions logged yet)")
        return
    lines = path.read_text(encoding='utf-8').strip().split('\n')[-limit:]
    for ln in reversed(lines):
        rec = json.loads(ln)
        t = datetime.fromisoformat(rec['started_at']).strftime('%Y-%m-%d %H:%M')
        print(f"{rec['mode']}({rec['total']}) | {rec['acc']}% | {t}")
