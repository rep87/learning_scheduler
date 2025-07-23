# -*- coding: utf-8 -*-
"""
Word‑Learning Scheduler  (v0.4.3‑stable)
========================================
Fully functional single‑file module.  Tested for:
  • quiz_random / quiz_wrong (audio → definition 4‑choice)
  • quiz_spelling (audio → typing, Levenshtein 1‑len tolerance)
  • word CRUD, speak_example, show_vocab, show_sessions
  • On‑the‑fly schema initialization so old DBs won't break
Run ws.help() after import to see public API.
"""
from __future__ import annotations

import json, random, sys, time, os, hashlib, tempfile
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

try:
    from gtts import gTTS
    from IPython.display import Audio, display
except ImportError:
    gTTS = None

# -------------------- globals ----------------------
BASE = Path.cwd() / 'learning_scheduler'
DATA_DIR = None
AUDIO_DIR = None
WORDS_FILE = None
SESSIONS_FILE = None

# -------------------- helpers ----------------------

def _now_iso():
    return datetime.utcnow().isoformat()


def _speak(text: str, tmp: bool = False):
    if gTTS is None:
        print('[TTS unavailable – install gTTS]'); return
    if tmp:
        fp = Path(tempfile.gettempdir()) / f"tmp_{hashlib.md5(text.encode()).hexdigest()}.mp3"
        gTTS(text).save(fp)
        display(Audio(fp, autoplay=True))
        try:
            fp.unlink()
        except OSError:
            pass
    else:
        fn = AUDIO_DIR / f"{text.lower()}.mp3"
        if not fn.exists():
            gTTS(text).save(fn)
        display(Audio(fn, autoplay=True))


def _lev(a: str, b: str) -> int:  # Levenshtein distance (simple)
    if a == b:
        return 0
    if not a or not b:
        return abs(len(a) - len(b))
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            ins = curr[j-1] + 1
            delt = prev[j] + 1
            sub = prev[j-1] + (ca != cb)
            curr.append(min(ins, delt, sub))
        prev = curr
    return prev[-1]

# -------------------- IO ---------------------------

def setup_dirs():
    global DATA_DIR, AUDIO_DIR, WORDS_FILE, SESSIONS_FILE
    BASE.mkdir(parents=True, exist_ok=True)
    DATA_DIR = BASE / 'data'; DATA_DIR.mkdir(exist_ok=True)
    AUDIO_DIR = DATA_DIR / 'audio_cache' / 'words_audio'; AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    WORDS_FILE = DATA_DIR / 'words.json'
    SESSIONS_FILE = DATA_DIR / 'quizzes.jsonl'
    if not WORDS_FILE.exists():
        WORDS_FILE.write_text('{}')


def _load_db() -> Dict:
    return json.loads(WORDS_FILE.read_text())


def _save_db(db: Dict):
    WORDS_FILE.write_text(json.dumps(db, ensure_ascii=False, indent=2))


def _ensure_schema(entry: Dict):
    if 'stats' not in entry:
        entry['stats'] = {
            'choice': {'correct': 0, 'wrong': 0, 'last': None},
            'spelling': {'correct': 0, 'wrong': 0, 'last': None},
            'recall': {'correct': 0, 'wrong': 0, 'last': None}
        }
    else:
        for m in ['choice', 'spelling', 'recall']:
            entry['stats'].setdefault(m, {'correct': 0, 'wrong': 0, 'last': None})
    if 'srs' not in entry:
        entry['srs'] = {'ef': 2.5, 'interval': 1, 'next_due': _now_iso()}

# -------------------- word API ---------------------

def add_word(word: str, definition_en: str, examples: List[str], tags: List[str]):
    db = _load_db()
    entry = db.get(word, {})
    entry.update({'definition_en': definition_en, 'examples': examples, 'tags': tags, 'added_at': entry.get('added_at', _now_iso())})
    _ensure_schema(entry)
    db[word] = entry
    _save_db(db)
    _speak(word)  # play pronunciation


def search_word(word: str):
    db = _load_db(); entry = db.get(word)
    if not entry:
        print('Not found'); return None
    _ensure_schema(entry)
    from pprint import pprint; pprint({word: entry}); return entry

find_word = search_word


def edit_word(word: str, **kwargs):
    db = _load_db(); entry = db.get(word)
    if not entry:
        print('Not found'); return
    entry.update(**kwargs); _save_db(db)


def delete_word(word: str):
    db = _load_db()
    if db.pop(word, None):
        _save_db(db); print('Deleted')

# -------------------- speak example ----------------

def speak_example(word: str, idx: int = 0):
    db = _load_db(); entry = db.get(word)
    if not entry:
        print('Not found'); return
    if idx >= len(entry['examples']):
        print('No such example'); return
    txt = entry['examples'][idx]
    print(txt)
    _speak(txt, tmp=True)

# -------------------- vocab view -------------------

def show_vocab(order: str = 'alpha'):
    db = _load_db()
    for v in db.values(): _ensure_schema(v)
    if order == 'wrong_desc':
        items = sorted(db.items(), key=lambda kv: kv[1]['stats']['choice']['wrong'], reverse=True)
    elif order == 'recent':
        items = sorted(db.items(), key=lambda kv: kv[1]['added_at'], reverse=True)
    else:
        items = sorted(db.items())
    for w, d in items:
        s = d['stats']
        print(f"{w:15} choice {s['choice']['correct']}/{s['choice']['wrong']} | spell {s['spelling']['correct']}/{s['spelling']['wrong']} | recall {s['recall']['correct']}/{s['recall']['wrong']}  {d['definition_en'][:60]}")

# -------------------- sessions view ----------------

def show_sessions(limit: int = 10):
    if not SESSIONS_FILE.exists():
        print('No sessions yet'); return
    lines = SESSIONS_FILE.read_text().strip().split('\n')[-limit:][::-1]
    for ln in lines:
        j = json.loads(ln)
        print(f"{j['mode']:8} | {j['total']:3} | {j['acc']:5}% | {j['duration_sec']:4}s | {j['started_at'][:16]}")

# -------------------- quiz helpers -----------------

def _write_session(mode: str, total: int, correct: int, start: float):
    sess = {
        'mode': mode,
        'total': total,
        'correct': correct,
        'acc': round(100*correct/total),
        'started_at': _now_iso(),
        'duration_sec': int(time.time()-start)
    }
    with SESSIONS_FILE.open('a') as f:
        f.write(json.dumps(sess)+'\n')


def _weighted_choice(words: List[str], weights: List[float], k: int) -> List[str]:
    import numpy as np
    weights = [max(w, 1e-3) for w in weights]
    probs = np.array(weights) / sum(weights)
    idxs = np.random.choice(range(len(words)), size=min(k, len(words)), replace=False, p=probs)
    return [words[i] for i in idxs]

# -------------------- quiz: random / wrong ---------

def quiz_random(n: int = 10):
    db = _load_db(); [ _ensure_schema(v) for v in db.values() ]
    words = list(db.keys())
    if not words:
        print('No words'); return
    questions = random.sample(words, min(n, len(words)))
    _quiz_choice(questions, db, mode='choice')


def quiz_wrong(n: int = 10):
    db = _load_db(); [ _ensure_schema(v) for v in db.values() ]
    words = list(db.keys())
    weights = [db[w]['stats']['choice']['wrong']+1 for w in words]
    questions = _weighted_choice(words, weights, n)
    _quiz_choice(questions, db, mode='choice')


def _quiz_choice(questions: List[str], db: Dict, mode: str):
    start = time.time(); correct = 0
    for w in questions:
        _speak(w)
        defs = [db[w]['definition_en']] + random.sample([db[x]['definition_en'] for x in db if x != w], k=min(3, len(db)-1))
        random.shuffle(defs)
        print('\n'.join([f"{i+1} {d}" for i, d in enumerate(defs)]))
        sys.stdout.flush(); time.sleep(0.01)
        choice = input("Your choice: ")
        idx = int(choice)-1 if choice.isdigit() else -1
        is_correct = idx>=0 and defs[idx]==db
