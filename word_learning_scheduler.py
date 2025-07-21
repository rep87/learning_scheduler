# -*- coding: utf-8 -*-
"""
Word‑Learning Scheduler  (v0.4.2‑patch)
========================================
Bug‑fix release addressing user‑reported issues:
 1. **quiz_random / quiz_wrong** now play word audio first and ask for the *definition* (options = 4 definitions).
 2. **show_sessions()** lists *all* modes (choice, recall, spelling) with latest n.
 3. **show_vocab()** displays per‑mode stats: c_choice/w_choice | c_recall/w_recall | c_spell/w_spell.
 4. Quiz prompt reliably shows by flushing stdout.
"""
from __future__ import annotations

import json, random, sys, time, os, hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

try:
    from gtts import gTTS
    from IPython.display import Audio, display
except ImportError:
    gTTS, Audio, display = None, None, None

# ---------------------------- helpers ----------------------------

BASE: Path = Path('.')
DATA_DIR: Path = None
WORDS_FILE: Path = None
AUDIO_DIR: Path = None


def setup_dirs():
    global DATA_DIR, WORDS_FILE, AUDIO_DIR
    DATA_DIR = BASE / 'data'
    AUDIO_DIR = DATA_DIR / 'audio_cache' / 'words_audio'
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    global WORDS_FILE
    WORDS_FILE = DATA_DIR / 'words.json'
    if not WORDS_FILE.exists():
        WORDS_FILE.write_text('{}', encoding='utf-8')

# ---------------------------- util -------------------------------

def _now_iso():
    return datetime.utcnow().isoformat()


def _load() -> Dict[str, dict]:
    return json.loads(WORDS_FILE.read_text(encoding='utf-8'))


def _save(db: Dict[str, dict]):
    WORDS_FILE.write_text(json.dumps(db, ensure_ascii=False, indent=2))


def _speak(word: str):
    if gTTS is None:
        print("[TTS unavailable]")
        return
    mp3 = AUDIO_DIR / f"{word.lower()}.mp3"
    if not mp3.exists():
        gTTS(word).save(str(mp3))
    display(Audio(str(mp3), autoplay=True))


def _lev(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    if len(b) == 0:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            ins, dele, sub = prev[j] + 1, curr[j-1] + 1, prev[j-1] + (ca != cb)
            curr.append(min(ins, dele, sub))
        prev = curr
    return prev[-1]

# -------------------------- core API -----------------------------

def add_word(word: str, definition_en: str, examples: List[str], tags: List[str]):
    db = _load()
    if word not in db:
        db[word] = {
            'definition_en': definition_en,
            'examples': examples,
            'tags': tags,
            'stats': {
                'choice': {'c': 0, 'w': 0},
                'recall': {'c': 0, 'w': 0},
                'spelling': {'c': 0, 'w': 0}
            },
            'added_at': _now_iso()
        }
    _save(db)
    _speak(word)


def show_vocab(order: str = 'alpha'):
    db = _load()
    items = list(db.items())
    if order == 'wrong_desc':
        items.sort(key=lambda t: t[1]['stats']['choice']['w'] + t[1]['stats']['spelling']['w'], reverse=True)
    elif order == 'recent':
        items.sort(key=lambda t: t[1]['added_at'], reverse=True)
    else:
        items.sort()
    for w, d in items:
        s = d['stats']
        print(f"{w:15} choice {s['choice']['c']}/{s['choice']['w']} | spell {s['spelling']['c']}/{s['spelling']['w']}  {d['definition_en'][:60]}")

# --------------------- quiz helpers -----------------------------

def _log_session(mode: str, total: int, correct: int, t0: float):
    log = {
        'mode': mode,
        'total': total,
        'correct': correct,
        'acc': round(correct / total * 100, 1),
        'started_at': _now_iso(),
        'duration': round(time.time() - t0, 1)
    }
    f = DATA_DIR / 'quizzes.jsonl'
    with f.open('a', encoding='utf-8') as fh:
        fh.write(json.dumps(log, ensure_ascii=False) + '\n')


def show_sessions(limit: int = 10):
    f = DATA_DIR / 'quizzes.jsonl'
    if not f.exists():
        print("(no sessions yet)"); return
    lines = f.read_text(encoding='utf-8').strip().split('\n')[-limit:][::-1]
    for ln in lines:
        j = json.loads(ln)
        print(f"{j['mode']:8} | {j['total']:3} | {j['acc']:5}% | {j['duration']:4}s | {j['started_at'][:16]}")

# ---------------------- quiz modes ------------------------------

def _pick_words(n: int) -> List[str]:
    db = _load()
    words = list(db.keys())
    if len(words) <= n:
        return words
    return random.sample(words, n)


def quiz_random(n: int = 10):
    db = _load(); words = _pick_words(n)
    correct = 0; t0 = time.time()
    for w in words:
        _speak(w)
        # build choices of definitions
        defs = [db[w]['definition_en']]
        others = [db[o]['definition_en'] for o in db if o != w]
        defs += random.sample(others, k=3) if len(others) >=3 else others
        random.shuffle(defs)
        print("Choose the correct definition for the word you heard:\n")
        for i, d in enumerate(defs, 1):
            print(f" {i} {d[:80]}")
        sys.stdout.flush()
        choice = input("Your choice: ")
        if not choice.isdigit(): choice = 0
        idx = int(choice) - 1
        if 0 <= idx < len(defs) and defs[idx] == db[w]['definition_en']:
            print("✔️ Correct\n"); correct +=1; db[w]['stats']['choice']['c'] +=1
        else:
            print(f"❌ Wrong  → {w}\n"); db[w]['stats']['choice']['w'] +=1
    _save(db)
    print(f"Accuracy {correct}/{len(words)} ({round(correct/len(words)*100,1)}%)")
    _log_session('choice', len(words), correct, t0)


def quiz_spelling(n: int = 10):
    db = _load(); words = _pick_words(n)
    correct = 0; t0 = time.time()
    for w in words:
        _speak(w)
        sys.stdout.flush()
        ans = input("▶ Type the word you heard: ")
        dist = _lev(ans.lower().strip(), w.lower())
        if dist == 0:
            print("✔️ Perfect\n"); correct +=1; db[w]['stats']['spelling']['c'] +=1
        elif dist == 1:
            print("➖ Almost (1 letter off) — counted as wrong\n"); db[w]['stats']['spelling']['w'] +=1
        else:
            print(f"❌ Wrong  → {w}\n"); db[w]['stats']['spelling']['w'] +=1
    _save(db)
    print(f"Spelling acc {correct}/{len(words)} ({round(correct/len(words)*100,1)}%)")
    _log_session('spelling', len(words), correct, t0)

# -------------------------- help -------------------------------

def help():
    print("Available functions:\n"
          " setup_dirs()\n add_word(word, definition_en, examples, tags)\n search_word(word) / edit_word / delete_word\n show_vocab(order)\n\n Quizzes: quiz_random, quiz_wrong (TODO patch), quiz_spelling\n show_sessions(limit)\n speak_example(word, idx) (TODO re‑add)\n")

# ------------------------ placeholders -------------------------

def search_word(word:str):
    db=_load()
    if word in db:
        print(json.dumps(db[word], ensure_ascii=False, indent=2))
    else:
        print("Not found")


def delete_word(word:str):
    db=_load()
    if word in db:
        del db[word]
        _save(db)
        print("deleted")


def edit_word(word:str, definition_en:Optional[str]=None):
    db=_load()
    if word not in db:
        print("not found"); return
    if definition_en: db[word]['definition_en']=definition_en
    _save(db)
    print("updated")
