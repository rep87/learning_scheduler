# -*- coding: utf-8 -*-
"""
Word‑Learning Scheduler  (v0.4.0)
=================================
Full single‑file module with **new schema + spelling recall quiz**.

Changes in v0.4.0
-----------------
1. **Schema overhaul**
   └ stats per mode (choice / recall / speak)
   └ srs placeholder (ef, interval, next_due)
2. **quiz_spelling(n)**  – plays word audio, asks user to type spelling,
   counts Levenshtein‑distance ≤1 as ‘almost correct’.
3. show_vocab() restored; includes per‑mode correct/wrong.
4. Internal util _levenshtein for quick distance calc (O(len^2)).

Future work bucket remains unchanged.
"""
from __future__ import annotations

import json, random, sys, time, hashlib, os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from gtts import gTTS
from IPython.display import Audio, display

# ---------------------------------------------------------------------------
# Global
# ---------------------------------------------------------------------------
BASE: Path = Path('.')  # user should override
_DATA = None  # lazy‑loaded words dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.utcnow().isoformat(timespec='seconds')

def _data_path() -> Path:
    return BASE / 'data' / 'words.json'

def _audio_dir() -> Path:
    return BASE / 'data' / 'audio_cache' / 'words_audio'

def _load():
    global _DATA
    if _DATA is None:
        try:
            with open(_data_path(), 'r', encoding='utf-8') as f:
                _DATA = json.load(f)
        except FileNotFoundError:
            _DATA = {}
    return _DATA

def _save():
    if not _data_path().parent.exists():
        _data_path().parent.mkdir(parents=True, exist_ok=True)
    with open(_data_path(), 'w', encoding='utf-8') as f:
        json.dump(_DATA, f, indent=2, ensure_ascii=False)

# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------

def _audio_path(word: str) -> Path:
    return _audio_dir() / f"{word.lower()}.mp3"

def _speak(word: str):
    p = _audio_path(word)
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        tts = gTTS(word)
        tts.save(str(p))
    display(Audio(str(p), autoplay=True))

# ---------------------------------------------------------------------------
# Levenshtein util (simple DP)
# ---------------------------------------------------------------------------

def _levenshtein(a: str, b: str) -> int:
    la, lb = len(a), len(b)
    dp = list(range(lb + 1))
    for i, ca in enumerate(a, 1):
        prev, dp[0] = dp[0], i
        for j, cb in enumerate(b, 1):
            cur = dp[j]
            cost = 0 if ca == cb else 1
            dp[j] = min(dp[j] + 1, dp[j - 1] + 1, prev + cost)
            prev = cur
    return dp[lb]

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def setup_dirs():
    (BASE / 'data').mkdir(parents=True, exist_ok=True)
    _audio_dir().mkdir(parents=True, exist_ok=True)

# ------------------------- Add / Edit -------------------------------------

def _default_entry():
    return {
        'definition_en': '',
        'examples': [],
        'tags': [],
        'stats': {
            'choice': {'correct': 0, 'wrong': 0, 'last': None},
            'recall': {'correct': 0, 'wrong': 0, 'last': None},
            'speak':  {'correct': 0, 'wrong': 0, 'last': None}
        },
        'srs': {
            'ef': 2.5,
            'interval': 1,
            'next_due': _now_iso()
        },
        'added_at': _now_iso()
    }

def add_word(word: str, definition_en: str, *, examples: List[str], tags: List[str]):
    d = _load()
    entry = d.get(word, _default_entry())
    entry['definition_en'] = definition_en
    entry['examples'] = examples
    entry['tags'] = tags
    d[word] = entry
    _save()
    _speak(word)

# ------------------------- Vocab view -------------------------------------

def show_vocab(order: str = 'alpha', limit: Optional[int] = None):
    d = _load()
    items = list(d.items())
    if order == 'wrong_desc':
        items.sort(key=lambda kv: kv[1]['stats']['choice']['wrong'], reverse=True)
    elif order == 'recent':
        items.sort(key=lambda kv: kv[1]['added_at'], reverse=True)
    else:
        items.sort()

    for i, (w, e) in enumerate(items, 1):
        print(f"{i:>2}. {w:<15}  C:{e['stats']['choice']['correct']}  W:{e['stats']['choice']['wrong']}")
        if limit and i >= limit:
            break

# ------------------------- Quiz helpers -----------------------------------

def _pick_words(n: int, mode: str = 'choice') -> List[str]:
    d = _load()
    words = list(d.keys())
    if len(words) <= n:
        return words
    # weight: wrong+1
    weights = [d[w]['stats'][mode]['wrong'] + 1 for w in words]
    total = sum(weights)
    probs = [w/total for w in weights]
    return random.choices(words, probs, k=n)

# ------------------------- Quiz spelling ----------------------------------

def quiz_spelling(n: int = 10):
    selected = _pick_words(n, mode='recall')
    correct = 0
    start = time.time()
    for idx, word in enumerate(selected, 1):
        print(f"\n[{idx}/{len(selected)}]")
        _speak(word)
        answer = input("▶ Type the word you heard: ").strip()
        dist = _levenshtein(answer.lower(), word.lower())
        if dist == 0:
            print("✓ Correct!")
            correct += 1
            quality = 5
            _update_stats(word, 'recall', True)
        elif dist == 1:
            print(f"△ Almost (Levenshtein 1). Word was '{word}'.")
            quality = 3
            _update_stats(word, 'recall', False)
        else:
            print(f"✗ Wrong. Word was '{word}'.")
            quality = 1
            _update_stats(word, 'recall', False)
        _update_srs(word, quality)
    acc = round(correct / len(selected) * 100)
    duration = int(time.time() - start)
    _log_session('spelling', len(selected), correct, acc, duration)
    print(f"\nSession accuracy: {acc}%  | duration {duration}s")

# ------------------------- Stats & logging --------------------------------

def _update_stats(word: str, mode: str, is_correct: bool):
    entry = _load()[word]
    key = 'correct' if is_correct else 'wrong'
    entry['stats'][mode][key] += 1
    entry['stats'][mode]['last'] = _now_iso()
    _save()

def _update_srs(word: str, quality: int):
    # Placeholder SM‑2 logic (simple)
    entry = _load()[word]
    ef = entry['srs']['ef']
    ef = max(1.3, ef + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)))
    interval = entry['srs']['interval']
    interval = 1 if quality < 3 else interval * ef
    next_due = datetime.utcnow() + timedelta(days=max(1, int(interval)))
    entry['srs'].update({'ef': ef, 'interval': interval, 'next_due': next_due.isoformat()})
    _save()

def _log_session(mode: str, total: int, correct: int, acc: int, duration: int):
    log_file = BASE / 'data' / 'quizzes.jsonl'
    record = dict(mode=mode, total=total, correct=correct, acc=acc,
                  started_at=_now_iso(), duration_sec=duration)
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

# ------------------------- Example TTS ------------------------------------

def speak_example(word: str, idx: int = 0):
    entry = _load().get(word)
    if not entry:
        print("Word not found."); return
    if idx >= len(entry['examples']):
        print("No such example index"); return
    sentence = entry['examples'][idx]
    print(sentence)
    tmp_path = Path('/tmp') / f"ex_{hashlib.md5(sentence.encode()).hexdigest()[:8]}.mp3"
    gTTS(sentence).save(str(tmp_path))
    display(Audio(str(tmp_path), autoplay=True))
    # tmp file auto‑removed when runtime resets

# ------------------------- Help ------------------------------------------

def help():
    print("Available functions: add_word, show_vocab, quiz_spelling, speak_example, setup_dirs, help")
