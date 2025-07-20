# -*- coding: utf-8 -*-
"""
Word‑Learning Scheduler (MVP v0.3.0)
====================================
New feature: **session‑level quiz logs & viewer**
------------------------------------------------
    • Each quiz call (random / wrong / recall) now logs: mode, total, correct, accuracy, timestamp, duration
    • Logs persisted in `quizzes.jsonl` inside BASE / data
    • `show_sessions(limit=10)`  → human‑readable list (latest first)

Patch fixes:
    • search_word() duplicate print fully removed (quiet=True)
"""
from __future__ import annotations

import json, random, sys, time, hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from gtts import gTTS
    from IPython.display import Audio, display
    _HAS_TTS = True
except ImportError:
    _HAS_TTS = False

__all__ = [
    "BASE", "setup_dirs", "add_word", "search_word", "find_word", "edit_word", "delete_word",
    "quiz_random", "quiz_wrong", "quiz_recall", "show_vocab", "show_stats", "show_sessions"
]

BASE: Path = Path('.')  # will be overwritten by user
_DATA: Dict[str, Dict] = {}
_WORDS_PATH: Path
_QUIZ_LOG_PATH: Path
_AUDIO_WORD_PATH: Path
_AUDIO_EX_PATH: Path

# -------------------- IO helpers -------------------- #

def setup_dirs():
    """Create data & cache directories and load DB on startup."""
    global _WORDS_PATH, _QUIZ_LOG_PATH, _AUDIO_WORD_PATH, _AUDIO_EX_PATH

    data_dir = BASE / 'data'
    audio_dir = data_dir / 'audio_cache'
    _AUDIO_WORD_PATH = audio_dir / 'words_audio'
    _AUDIO_EX_PATH = audio_dir / 'examples_audio'

    for p in (_AUDIO_WORD_PATH, _AUDIO_EX_PATH):
        p.mkdir(parents=True, exist_ok=True)
    _WORDS_PATH = data_dir / 'words.json'
    _QUIZ_LOG_PATH = data_dir / 'quizzes.jsonl'
    data_dir.mkdir(parents=True, exist_ok=True)

    if _WORDS_PATH.exists():
        with open(_WORDS_PATH, 'r', encoding='utf-8') as fp:
            _DATA.update(json.load(fp))


def _save_db():
    with open(_WORDS_PATH, 'w', encoding='utf-8') as fp:
        json.dump(_DATA, fp, ensure_ascii=False, indent=2)


def _speak(text: str):
    if not _HAS_TTS:
        return
    key = hashlib.md5(text.encode()).hexdigest()[:16]
    mp3 = _AUDIO_WORD_PATH / f"{key}.mp3"
    if not mp3.exists():
        gTTS(text).save(mp3)
    display(Audio(str(mp3), autoplay=True))

# -------------------- CRUD -------------------- #

def add_word(word: str, definition_en: str, examples: List[str] | None = None, *, tags: List[str] | None = None):
    """Insert or update a word entry and play its pronunciation."""
    w = word.lower().strip()
    entry = _DATA.get(w, {
        'definition_en': '', 'examples': [], 'tags': [],
        'correct_cnt': 0, 'wrong_cnt': 0,
        'added_at': datetime.utcnow().isoformat(timespec='seconds')
    })
    entry['definition_en'] = definition_en
    if examples:
        entry['examples'] = examples
    if tags:
        entry['tags'] = tags
    _DATA[w] = entry
    _save_db()
    _speak(w)


def search_word(word: str, *, display: bool = True):
    w = word.lower().strip()
    entry = _DATA.get(w)
    if not entry:
        if display:
            print(f"{w!r} not found.")
        return None
    if display:
        print(w)
        for k, v in entry.items():
            print(f"  ├ {k:<12}: {v}")
    return entry

find_word = search_word  # alias


def edit_word(word: str, **updates):
    entry = search_word(word, display=False)
    if entry is None:
        print("No such word.")
        return
    entry.update({k: v for k, v in updates.items() if k in entry})
    _save_db()
    print("Updated.")


def delete_word(word: str):
    if _DATA.pop(word.lower().strip(), None):
        _save_db()
        print("Deleted.")
    else:
        print("Word not found.")

# -------------------- Quiz helpers -------------------- #

def _weighted_choice(words: List[str], n: int, unique: bool) -> List[str]:
    weights = []
    for w in words:
        d = _DATA[w]
        weights.append(d['wrong_cnt'] + 1 / (d['correct_cnt'] + 1))
    chosen = random.choices(words, weights=weights, k=n if not unique else n * 2)
    # ensure uniqueness if requested
    if unique:
        uniq = []
        for w in chosen:
            if w not in uniq:
                uniq.append(w)
            if len(uniq) == n:
                break
        return uniq
    return chosen[:n]


def _make_choices(target: str) -> Tuple[List[str], int]:
    options = [target]
    all_words = list(_DATA.keys())
    all_words.remove(target)
    options.extend(random.sample(all_words, k=min(3, len(all_words))))
    random.shuffle(options)
    return options, options.index(target)


def _log_session(mode: str, total: int, correct: int, started_at: float, finished_at: float):
    if not _QUIZ_LOG_PATH.parent.exists():
        return
    rec = {
        'mode': mode,
        'total': total,
        'correct': correct,
        'accuracy': round(correct / total * 100, 1),
        'started_at': datetime.fromtimestamp(started_at).isoformat(timespec='seconds'),
        'duration_sec': round(finished_at - started_at, 2)
    }
    with open(_QUIZ_LOG_PATH, 'a', encoding='utf-8') as fp:
        fp.write(json.dumps(rec, ensure_ascii=False) + "\n")

# -------------------- Quiz modes -------------------- #

def quiz_random(n: int = 10, *, unique: bool = True):
    start = time.time()
    words = _weighted_choice(list(_DATA.keys()), n, unique)
    correct = 0
    for w in words:
        _speak(w)
        choices, answer_idx = _make_choices(w)
        print(f"\n[{w.upper()}] definition?")
        for i, c in enumerate(choices):
            print(f"  {i+1}. {_DATA[c]['definition_en']}")
        resp = input("Choose 1-4: ")
        if resp.strip() == str(answer_idx + 1):
            print("✔ Correct\n")
            _DATA[w]['correct_cnt'] += 1
            correct += 1
        else:
            print(f"❌ Wrong (answer: {answer_idx + 1})\n")
            _DATA[w]['wrong_cnt'] += 1
    _save_db()
    acc = round(correct / len(words) * 100, 1)
    end = time.time()
    print(f"=== Result: {correct}/{len(words)}  ({acc}%) ===")
    _log_session('random', len(words), correct, start, end)


def quiz_wrong(n: int = 10):
    wrong_words = [w for w, d in _DATA.items() if d['wrong_cnt'] > 0]
    if not wrong_words:
        print("No wrong words yet.")
        return
    m = min(n, len(wrong_words))
    quiz_random(m, unique=True)


def quiz_recall(n: int = 10):
    start = time.time()
    words = _weighted_choice(list(_DATA.keys()), n, unique=True)
    correct = 0
    for w in words:
        defn = _DATA[w]['definition_en']
        ans = input(f"[Recall] {defn}\nType the word: ")
        if ans.strip().lower() == w:
            print("✔ Correct\n"); correct += 1; _DATA[w]['correct_cnt'] += 1
        else:
            print(f"❌ Wrong (answer: {w})\n"); _DATA[w]['wrong_cnt'] += 1
    _save_db()
    acc = round(correct / len(words) * 100, 1)
    end = time.time()
    print(f"=== Recall Result: {correct}/{len(words)} ({acc}%) ===")
    _log_session('recall', len(words), correct, start, end)

# -------------------- Views -------------------- #

def show_vocab(order: str = 'wrong_desc'):
    entries = list(_DATA.items())
    if order == 'wrong_desc':
        entries.sort(key=lambda x: x[1]['wrong_cnt'], reverse=True)
    print("word | correct | wrong | acc%")
    for w, d in entries:
        tot = d['correct_cnt'] + d['wrong_cnt']
        acc = 0 if tot == 0 else round(d['correct_cnt']/tot*100,1)
        print(f"{w:>15} | {d['correct_cnt']:>3} | {d['wrong_cnt']:>3} | {acc:>5}")


def show_stats():
    tot_correct = sum(d['correct_cnt'] for d in _DATA.values())
    tot_wrong = sum(d['wrong_cnt'] for d in _DATA.values())
    tot = tot_correct + tot_wrong
    acc = 0 if tot == 0 else round(tot_correct / tot * 100, 1)
    print(f"Total attempts: {tot} (correct {tot_correct}, wrong {tot_wrong}, accuracy {acc}%)")


def show_sessions(limit: int = 10):
    if not _QUIZ_LOG_PATH.exists():
        print("No sessions recorded yet.")
        return
    lines = _QUIZ_LOG_PATH.read_text(encoding='utf-8').strip().splitlines()[-limit:][::-1]
    for ln in lines:
        rec = json.loads(ln)
        ts = datetime.fromisoformat(rec['started_at']).strftime('%Y-%m-%d %H:%M')
        print(f"{rec['mode'].capitalize()}({rec['total']}) | {rec['accuracy']}% | {ts}")
