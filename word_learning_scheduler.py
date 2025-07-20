# -*- coding: utf-8 -*-
"""
Word‑Learning Scheduler (MVP v0.2.2)
====================================
Patch notes (2025‑07‑21):
    • search_word(): single pretty‑print (no duplicate)
    • add_word(): automatically plays word‑level TTS on successful insert/update
"""
from __future__ import annotations

import json, random, sys, time, hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# --- gTTS & Colab audio
try:
    from gtts import gTTS
    from IPython.display import Audio, display
except ImportError:
    gTTS = None  # type: ignore
    def Audio(*args, **kwargs):
        raise ImportError("Please `pip install gtts` in Colab")
    def display(x):
        pass

BASE: Path = Path.cwd()
DATA_PATH: Path
AUDIO_WORDS: Path
AUDIO_EXAMPLES: Path
DB_FILE: Path
QUIZ_LOG: Path

def setup_dirs():
    """Create directory tree & global constants."""
    global DATA_PATH, AUDIO_WORDS, AUDIO_EXAMPLES, DB_FILE, QUIZ_LOG
    DATA_PATH = BASE / "data"
    AUDIO_WORDS = DATA_PATH / "audio_cache" / "words_audio"
    AUDIO_EXAMPLES = DATA_PATH / "audio_cache" / "examples_audio"
    DB_FILE = DATA_PATH / "words.json"
    QUIZ_LOG = DATA_PATH / "quizzes.jsonl"
    for p in [AUDIO_WORDS, AUDIO_EXAMPLES]:
        p.mkdir(parents=True, exist_ok=True)
    DATA_PATH.mkdir(parents=True, exist_ok=True)
    if not DB_FILE.exists():
        DB_FILE.write_text("{}")

def _load() -> Dict[str, Dict]:
    return json.loads(DB_FILE.read_text())

def _save(db: Dict):
    DB_FILE.write_text(json.dumps(db, ensure_ascii=False, indent=2))

def _tts_cache(text: str, dest_path: Path):
    if dest_path.exists():
        return dest_path
    if gTTS is None:
        return dest_path  # gTTS missing
    tts = gTTS(text)
    tts.save(dest_path.as_posix())
    return dest_path

def _speak(text: str, category: str = "word", autoplay: bool = True):
    """Play cached audio (generate if absent)."""
    if category == "word":
        fname = f"{text.lower()}.mp3"
        path = AUDIO_WORDS / fname
    else:
        fname = hashlib.md5(text.encode()).hexdigest() + ".mp3"
        path = AUDIO_EXAMPLES / fname
    _tts_cache(text, path)
    try:
        display(Audio(path.as_posix(), autoplay=autoplay))
    except Exception:
        pass

# ----- Public API -----

def add_word(*, word: str, definition_en: str, examples: Optional[List[str]] = None, tags: Optional[List[str]] = None):
    db = _load()
    entry = db.get(word, {
        "definition_en": definition_en,
        "examples": examples or [],
        "tags": tags or ["AI"],
        "correct_cnt": 0,
        "wrong_cnt": 0,
        "added_at": datetime.utcnow().isoformat(),
    })
    # update fields if provided
    entry["definition_en"] = definition_en or entry["definition_en"]
    if examples:
        entry["examples"] = examples
    if tags:
        entry["tags"] = tags
    db[word] = entry
    _save(db)
    _speak(word)  # auto play pronunciation on insert/update
    print(f"[+] Saved word: {word}")

# Search / lookup

def search_word(word: str, *, display: bool = True):
    db = _load()
    entry = db.get(word)
    if entry is None:
        print(f"[!] '{word}' not found.")
        return None
    if display:
        print(word)
        for k, v in entry.items():
            print(f"  ├ {k:<13}: {v}")
    return entry
# alias
find_word = search_word

# Delete

def delete_word(word: str):
    db = _load()
    if word in db:
        db.pop(word)
        _save(db)
        print(f"[-] Deleted '{word}'")
    else:
        print(f"[!] '{word}' not found")

# Edit

def edit_word(word: str, **fields):
    db = _load()
    if word not in db:
        print(f"[!] '{word}' not found")
        return
    db[word].update({k: v for k, v in fields.items() if v is not None})
    _save(db)
    print(f"[*] Updated '{word}'")

# Quiz helpers

def _weighted_sample(db: Dict[str, Dict], n: int, unique: bool = True):
    words = list(db.keys())
    weights = [db[w]["wrong_cnt"] + 1 / (db[w]["correct_cnt"] + 1) for w in words]
    chosen = []
    for _ in range(n):
        if unique and len(chosen) == len(words):
            break
        word = random.choices(words, weights)[0]
        if unique and word in chosen:
            continue
        chosen.append(word)
    return chosen

def quiz_random(n: int = 5, *, unique: bool = True):
    db = _load()
    if not db:
        print("[!] No words in DB")
        return
    target_words = _weighted_sample(db, n, unique=unique)
    _run_mcq(db, target_words)

def quiz_wrong(n: int = 5):
    db = _load()
    wrong_words = [w for w, v in db.items() if v["wrong_cnt"] > 0]
    if not wrong_words:
        print("[!] No wrong words, good job!")
        return quiz_random(n)
    target_words = wrong_words if len(wrong_words) < n else random.sample(wrong_words, n)
    _run_mcq(db, target_words)

def _run_mcq(db: Dict[str, Dict], target_words: List[str]):
    correct = 0
    for word in target_words:
        entry = db[word]
        _speak(word)
        # create choices
        other_words = [w for w in db.keys() if w != word]
        distractors = random.sample(other_words, k=3) if len(other_words) >= 3 else other_words
        options = [word] + distractors
        random.shuffle(options)
        print("\nWhich word matches the definition below?\n")
        print(entry["definition_en"])
        for idx, opt in enumerate(options, 1):
            print(f"  {idx}. {opt}")
        ans = input("Your choice (1‑4): ")
        try:
            choice = options[int(ans) - 1]
        except (ValueError, IndexError):
            choice = None
        if choice == word:
            print("✅ Correct!")
            correct += 1
            db[word]["correct_cnt"] += 1
        else:
            print(f"❌ Wrong. Correct answer: {word}")
            db[word]["wrong_cnt"] += 1
        _save(db)
    print(f"\nSession finished: {correct}/{len(target_words)} correct ( {correct/len(target_words)*100:.1f}% )")

# Recall mode (type‑in)

def quiz_recall(n: int = 5):
    db = _load()
    target_words = _weighted_sample(db, n, unique=True)
    correct = 0
    for word in target_words:
        _speak(word)
        answer = input(f"Define '{word}' in English (press Enter to skip): \n")
        if answer.strip():
            correct += 1  # accept any attempt as recall for MVP
        db[word]["correct_cnt"] += 1 if answer.strip() else 0
        _save(db)
    print(f"Recall session complete: {correct}/{len(target_words)} attempted.")

# Vocab / stats

def show_vocab(order: str = "wrong_desc"):
    db = _load()
    if order == "wrong_desc":
        items = sorted(db.items(), key=lambda x: x[1]["wrong_cnt"], reverse=True)
    else:
        items = db.items()
    for w, v in items:
        print(f"{w:<20} | wrong:{v['wrong_cnt']:<3} correct:{v['correct_cnt']:<3}")

def show_stats():
    db = _load()
    total = len(db)
    attempted = sum(v["correct_cnt"] + v["wrong_cnt"] for v in db.values())
    wrong_top = sorted(db.items(), key=lambda x: x[1]["wrong_cnt"], reverse=True)[:5]
    print(f"Total words: {total}\nTotal attempts: {attempted}")
    print("Top wrong words:")
    for w, v in wrong_top:
        print(f"  {w} → wrong {v['wrong_cnt']} / correct {v['correct_cnt']}")
