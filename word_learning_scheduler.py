# -*- coding: utf-8 -*-
"""
Word‑Learning Scheduler  (v0.4.1‑full)
======================================
Complete single‑file module with all public APIs restored.
Use ws.help() inside Colab to see the callable surface.
"""
from __future__ import annotations

import json, random, sys, time, os, hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

try:
    from IPython.display import Audio, display
except ImportError:
    Audio = None
    def display(x):
        print("[display placeholder]", x)

try:
    from gtts import gTTS
except ImportError:
    gTTS = None

# ---------------------------------------------------------------------------
BASE: Path = Path('.')  # caller should overwrite then call setup_dirs()
DATA_DIR: Path = Path('.')
WORDS_JSON: Path = Path('.')
WORDS_AUDIO_DIR: Path = Path('.')

# ---------------------------------------------------------------------------
# Helper --------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.utcnow().isoformat(timespec='seconds')

# very simple Levenshtein (distance 1 allowed for almost correct)
_def = None

def _lev(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    if len(b) == 0:
        return len(a)
    previous_row = range(len(b) + 1)
    for i, ca in enumerate(a):
        current_row = [i + 1]
        for j, cb in enumerate(b):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (ca != cb)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]

# ---------------------------------------------------------------------------
# Core persistence -----------------------------------------------------------

def setup_dirs():
    global DATA_DIR, WORDS_JSON, WORDS_AUDIO_DIR
    DATA_DIR = BASE / 'data'
    WORDS_AUDIO_DIR = DATA_DIR / 'audio_cache' / 'words_audio'
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    WORDS_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    WORDS_JSON = DATA_DIR / 'words.json'
    if not WORDS_JSON.exists():
        WORDS_JSON.write_text('{}', encoding='utf-8')


def _load() -> Dict:
    return json.loads(WORDS_JSON.read_text(encoding='utf-8'))


def _save(db: Dict):
    WORDS_JSON.write_text(json.dumps(db, ensure_ascii=False, indent=2))

# ---------------------------------------------------------------------------
# Audio ----------------------------------------------------------------------

def _word_mp3_path(word: str) -> Path:
    return WORDS_AUDIO_DIR / f"{word.lower()}.mp3"


def _speak(word: str):
    if gTTS is None or Audio is None:
        return
    path = _word_mp3_path(word)
    if not path.exists():
        gTTS(word).save(str(path))
    display(Audio(str(path), autoplay=True))


def speak_example(word: str, idx: int = 0):
    db = _load()
    entry = db[word]
    if idx >= len(entry['examples']):
        print('No example index')
        return
    text = entry['examples'][idx]
    print(text)
    if gTTS and Audio:
        tmp = Path('/tmp') / f"ex_{hashlib.md5(text.encode()).hexdigest()}.mp3"
        gTTS(text).save(tmp)
        display(Audio(str(tmp), autoplay=True))
        try:
            tmp.unlink()
        except OSError:
            pass

# ---------------------------------------------------------------------------
# Add / edit / delete --------------------------------------------------------

def add_word(*, word: str, definition_en: str, examples: List[str], tags: List[str]):
    db = _load()
    db[word] = {
        'definition_en': definition_en,
        'examples': examples,
        'tags': tags,
        'stats': {
            'choice':  { 'correct': 0, 'wrong': 0, 'last': None },
            'recall':  { 'correct': 0, 'wrong': 0, 'last': None },
            'speak':   { 'correct': 0, 'wrong': 0, 'last': None },
        },
        'srs': { 'ef': 2.5, 'interval': 1, 'next_due': _now_iso() },
        'added_at': _now_iso()
    }
    _save(db)
    _speak(word)


def search_word(word: str, display_entry: bool = True):
    db = _load()
    if word not in db:
        print('Not found')
        return None
    if display_entry:
        print(word)
        for k, v in db[word].items():
            if k in ('definition_en', 'added_at'):
                print(f"  ├ {k}: {v}")
        print()
    return db[word]

find_word = search_word


def edit_word(word: str, **fields):
    db = _load()
    if word not in db:
        print('Not found'); return
    db[word].update(fields)
    _save(db)


def delete_word(word: str):
    db = _load()
    if db.pop(word, None) is not None:
        _save(db)
        path = _word_mp3_path(word);
        try: path.unlink()
        except OSError: pass

# ---------------------------------------------------------------------------
# Quiz helpers ---------------------------------------------------------------

def _pick_words(n: int, mode: str = 'choice') -> List[str]:
    db = _load()
    if n >= len(db):
        return list(db.keys())
    keys = list(db.keys())
    random.shuffle(keys)
    return keys[:n]


def _record(db, word, kind, correct):
    stat = db[word]['stats'][kind]
    stat['correct' if correct else 'wrong'] += 1
    stat['last'] = _now_iso()

# Multiple‑choice ------------------------------------------------------------

def quiz_random(n: int = 10):
    _quiz_choice(n, mode='random')

def quiz_wrong(n: int = 10):
    _quiz_choice(n, mode='wrong')

def _quiz_choice(n: int, mode: str):
    db = _load()
    words = _pick_words(n)
    correct_total = 0
    for word in words:
        _speak(word)
        options = [word] + random.sample([w for w in db if w != word], 3)
        random.shuffle(options)
        print(f"\n>>>> {db[word]['definition_en']}")
        for i, opt in enumerate(options, 1):
            print(i, opt)
        ans = input('Your choice: ')
        try: idx = int(ans) - 1
        except ValueError: idx = -1
        chosen = options[idx] if 0 <= idx < 4 else None
        is_correct = (chosen == word)
        if is_correct:
            print('✓ Correct')
            correct_total += 1
        else:
            print(f"✗ Wrong (answer: {word})")
        _record(db, word, 'choice', is_correct)
    _save(db)
    print(f"\nResult: {correct_total}/{len(words)}  ({correct_total*100//len(words)}%)")

# Spelling recall ------------------------------------------------------------

def quiz_spelling(n: int = 10):
    db = _load()
    words = _pick_words(n)
    correct_total = 0
    for word in words:
        _speak(word)
        guess = input('▶ Type the word you heard: ').strip()
        dist = _lev(guess.lower(), word.lower())
        is_correct = dist == 0
        almost = dist == 1
        if is_correct:
            print('✓ Correct')
            correct_total += 1
        elif almost:
            print(f'~ Almost ({word})')
        else:
            print(f'✗ Wrong ({word})')
        _record(db, word, 'recall', is_correct)
    _save(db)
    print(f"\nSpelling result: {correct_total}/{len(words)}  ({correct_total*100//len(words)}%)")

# Sessions log & vocab -------------------------------------------------------
QUIZ_LOG: Path = None  # initialised below

def _log_session(mode: str, total: int, correct: int, duration: float):
    global QUIZ_LOG
    if QUIZ_LOG is None:
        QUIZ_LOG = DATA_DIR / 'quizzes.jsonl'
    entry = dict(mode=mode, total=total, correct=correct, acc=round(correct/total*100), started_at=_now_iso(), duration_sec=int(duration))
    QUIZ_LOG.open('a').write(json.dumps(entry)+'\n')


def show_vocab(order: str = 'alpha'):
    db = _load()
    items = list(db.items())
    if order == 'wrong_desc':
        items.sort(key=lambda kv: kv[1]['stats']['choice']['wrong'], reverse=True)
    elif order == 'recent':
        items.sort(key=lambda kv: kv[1]['added_at'], reverse=True)
    else:
        items.sort(key=lambda kv: kv[0])
    for w, info in items:
        wrong = info['stats']['choice']['wrong']
        correct = info['stats']['choice']['correct']
        print(f"{w:15}  c:{correct}  w:{wrong}  {info['definition_en'][:40]}")


def show_sessions(limit: int = 10):
    path = DATA_DIR / 'quizzes.jsonl'
    if not path.exists():
        print('No sessions'); return
    lines = path.read_text().strip().split('\n')[-limit:][::-1]
    for line in lines:
        e = json.loads(line)
        print(f"{e['mode']:<8}({e['total']}) | {e['acc']:3}% | {e['started_at']} | {e['duration_sec']}s")

# help -----------------------------------------------------------------------

def help():
    print("Public APIs:")
    print(" add_word, search_word, edit_word, delete_word")
    print(" quiz_random, quiz_wrong, quiz_spelling")
    print(" show_vocab, show_sessions, speak_example")
    print(" setup_dirs (call after setting ws.BASE)")
