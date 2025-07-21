# -*- coding: utf-8 -*-
"""
Word‑Learning Scheduler  (v0.3.3)
=================================
Single‑file package importable from Colab.  *Full listing*

Key features
------------
* Persist word database with per‑word stats & tags              →  data/words.json
* Cache word‑level TTS audio (gTTS) once on insertion           →  data/audio_cache/words_audio/
* On‑demand example TTS (no caching, tmp only) via speak_example()
* Quiz modes: multiple‑choice, wrong‑only, recall(type‑in)
* Session logs (mode / total / correct / acc / duration)        →  data/quizzes.jsonl
* Word list viewer show_vocab()  with sorting options

Usage pattern
-------------
>>> import word_learning_scheduler as ws
>>> ws.BASE = Path('/content/drive/MyDrive/Projects/learning_scheduler')
>>> ws.setup_dirs()
>>> ws.add_word('tensor', 'A multidimensional array...', examples=[...])
>>> ws.quiz_random(n=10)
>>> ws.show_sessions()

v0.3.3 patch (2025‑07‑21)
-------------------------
* Full file dumped so users can sync with GitHub without missing helpers
* Restored helper _now_iso()
* show_vocab() revived  (order='alpha'|'wrong_desc'|'recent')
* Fixed _speak() to actually play audio in Colab (display(Audio(...)))
* Quiz input prompt now reliably flushes stdout
"""
from __future__ import annotations

import json
import random
import sys
import time
import hashlib
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from gtts import gTTS
from IPython.display import Audio, display

# ------------------------------
# Global config / paths
# ------------------------------
BASE: Path = Path("./learning_scheduler")  # to be overridden by user
DATA_DIRNAME = "data"
AUDIO_DIRNAME = "audio_cache"
WORD_AUDIO_DIRNAME = "words_audio"

# ------------------------------
# Utility helpers
# ------------------------------

def _now_iso() -> str:
    """UTC ISO timestamp string."""
    return datetime.utcnow().isoformat(timespec="seconds")


def _ensure_dirs():
    global BASE
    (BASE / DATA_DIRNAME / AUDIO_DIRNAME / WORD_AUDIO_DIRNAME).mkdir(parents=True, exist_ok=True)

# ------------------------------
# Database loading / saving
# ------------------------------

def _db_path() -> Path:
    return BASE / DATA_DIRNAME / "words.json"


def _load_db() -> Dict[str, Dict]:
    path = _db_path()
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_db(db: Dict[str, Dict]):
    with open(_db_path(), "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

# ------------------------------
# TTS helpers
# ------------------------------

def _word_audio_path(word: str) -> Path:
    return BASE / DATA_DIRNAME / AUDIO_DIRNAME / WORD_AUDIO_DIRNAME / f"{word.lower()}.mp3"

def _speak(text: str, cache_path: Optional[Path] = None, autoplay: bool = True):
    """Speak text. If cache_path provided and exists, reuse; else generate."""
    if cache_path is not None and cache_path.exists():
        audio_path = cache_path
    else:
        audio_obj = gTTS(text)
        if cache_path is None:
            # tmp file
            tmp_name = f"/tmp/tts_{hashlib.md5(text.encode()).hexdigest()[:8]}.mp3"
            audio_path = Path(tmp_name)
        else:
            audio_path = cache_path
        audio_obj.save(str(audio_path))
    if autoplay:
        display(Audio(str(audio_path), autoplay=True))

# ------------------------------
# Public API
# ------------------------------

def setup_dirs():
    """Call once after setting BASE. Creates folder tree & default files."""
    _ensure_dirs()
    # initialise empty db if not exists
    if not _db_path().exists():
        _save_db({})
    # ensure quizzes log file exists
    log_path = BASE / DATA_DIRNAME / "quizzes.jsonl"
    if not log_path.exists():
        log_path.touch()


def add_word(word: str, definition_en: str, *, examples: Optional[List[str]] = None, tags: Optional[List[str]] = None):
    """Insert or update a word. Plays pronunciation once."""
    db = _load_db()
    entry = db.get(word, {
        "definition_en": definition_en,
        "examples": examples or [],
        "tags": tags or [],
        "correct_cnt": 0,
        "wrong_cnt": 0,
        "added_at": _now_iso(),
    })
    # update definition/examples if provided
    entry["definition_en"] = definition_en
    if examples:
        entry["examples"] = examples
    if tags:
        entry["tags"] = tags
    db[word] = entry
    _save_db(db)

    # cache & play audio
    audio_path = _word_audio_path(word)
    _speak(word, cache_path=audio_path)


def search_word(word: str, *, display_: bool = True):
    db = _load_db()
    entry = db.get(word)
    if entry and display_:
        print(f"{word}\n  ├ definition_en: {entry['definition_en']}\n  ├ examples     : {entry['examples']}\n  ├ tags         : {entry['tags']}\n  ├ correct_cnt  : {entry['correct_cnt']}\n  ├ wrong_cnt    : {entry['wrong_cnt']}\n  ├ added_at     : {entry['added_at']}")
    elif not entry and display_:
        print("[!] Word not found")
    return entry

# alias for user convenience
find_word = search_word

# ------------------------------
# show_vocab
# ------------------------------

def show_vocab(order: str = "alpha", top: Optional[int] = None):
    """Print word list sorted by 'alpha', 'wrong_desc', or 'recent'."""
    db = _load_db()
    items = list(db.items())
    if order == "wrong_desc":
        items.sort(key=lambda kv: kv[1]["wrong_cnt"], reverse=True)
    elif order == "recent":
        items.sort(key=lambda kv: kv[1]["added_at"], reverse=True)
    else:
        items.sort(key=lambda kv: kv[0])

    if top:
        items = items[:top]
    for w, e in items:
        print(f"{w:<20}  wrong:{e['wrong_cnt']}  correct:{e['correct_cnt']}")

# ------------------------------
# Example TTS on‑demand
# ------------------------------

def speak_example(word: str, idx: int = 0):
    entry = search_word(word, display_=False)
    if not entry:
        print("[!] Word not found")
        return
    examples = entry.get("examples", [])
    if not examples:
        print("[!] No examples stored for this word")
        return
    if idx >= len(examples):
        print(f"[!] Example index out of range (0‑{len(examples)-1})")
        return
    ex = examples[idx]
    print(f"Example[{idx}]: {ex}")
    _speak(ex)

# ------------------------------
# Quiz utilities
# ------------------------------

def _weighted_choice(db: Dict[str, Dict], mode: str) -> List[str]:
    words = list(db.keys())
    if mode == "wrong_only":
        words = [w for w in words if db[w]["wrong_cnt"] > 0]
        if not words:
            # fallback
            words = list(db.keys())
    weights = [db[w]["wrong_cnt"] + 1 for w in words]
    return random.choices(words, weights=weights, k=len(words))


def _ask(mc_word: str, db: Dict[str, Dict]):
    correct_def = db[mc_word]["definition_en"]
    # Get 3 distractors
    distractors = random.sample([db[w]["definition_en"] for w in db if w != mc_word], k=min(3, len(db)-1))
    options = distractors + [correct_def]
    random.shuffle(options)
    # Print question
    print("‑"*60)
    sys.stdout.flush()
    print(f"Word: {mc_word}")
    sys.stdout.flush()
    for i,opt in enumerate(options,1):
        print(f"  {i}. {opt}")
    sys.stdout.flush()
    # answer input
    ans = input("Choose (1‑4): ")
    try:
        ans_idx = int(ans.strip())
    except:
        ans_idx = 0
    is_correct = (options[ans_idx-1] == correct_def) if 1 <= ans_idx <= 4 else False
    print("✔ Correct!" if is_correct else f"✘ Wrong.  → {correct_def}")
    return is_correct


def _log_session(mode: str, total: int, correct: int, duration: float):
    log_entry = {
        "mode": mode,
        "total": total,
        "correct": correct,
        "acc": round(correct/total*100,1),
        "started_at": _now_iso(),
        "duration_sec": int(duration)
    }
    log_path = BASE / DATA_DIRNAME / "quizzes.jsonl"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False)+"\n")


def quiz_random(n: int = 10):
    _quiz("random", n)


def quiz_wrong(n: int = 10):
    _quiz("wrong_only", n)


def _quiz(mode: str, n: int):
    db = _load_db()
    if len(db) < 2:
        print("[!] Not enough words in DB. Add more first.")
        return
    words_order = _weighted_choice(db, mode)
    words_order = list(dict.fromkeys(words_order))  # deduplicate preserve order
    words_order = words_order[:n]

    correct = 0
    start = time.time()
    for w in words_order:
        _speak(w, cache_path=_word_audio_path(w), autoplay=True)
        if _ask(w, db):
            correct += 1
            db[w]["correct_cnt"] += 1
        else:
            db[w]["wrong_cnt"] += 1
        _save_db(db)
    duration = time.time()-start
    print(f"\nResult: {correct}/{len(words_order)}  → {round(correct/len(words_order)*100,1)}%  (time {int(duration)} s)")
    _log_session(mode, len(words_order), correct, duration)

# recall mode can be added later

# ------------------------------
# Session stats viewer
# ------------------------------

def show_sessions(limit: int = 20):
    log_path = BASE / DATA_DIRNAME / "quizzes.jsonl"
    if not log_path.exists():
        print("No sessions logged yet.")
        return
    with open(log_path, "r", encoding="utf-8") as f:
        lines = f.readlines()[-limit:]
    for line in reversed(lines):
        e = json.loads(line)
        print(f"{e['mode'].capitalize():<10}({e['total']}) | {e['acc']:>5}% | {e['started_at']} | {e['duration_sec']} s")

# ------------------------------
# Minimal help
# ------------------------------

def help():
    print("Available top‑level functions:")
    for name in [
        "setup_dirs", "add_word", "search_word / find_word",
        "show_vocab", "speak_example",
        "quiz_random", "quiz_wrong", "show_sessions"
    ]:
        print(" •", name)

