# -*- coding: utf-8 -*-
"""
Word‑Learning Scheduler (MVP v0.2)
==================================
Single‑file package importable from Colab.

Phase‑1 features:
    • Persist word DB (JSON) with per‑word stats & tags
    • Cache TTS audio for *words* on insertion (gTTS → mp3)
    • Optional on‑demand TTS for example sentences
    • Quiz modes: multiple‑choice, wrong‑only, recall(type‑in)
    • Basic SRS‑friendly weight (wrong_cnt priority)
    • Word lookup / edit / delete   ◀ NEW

Public API (stable):
    setup_dirs, add_word, search_word, edit_word, delete_word,
    quiz_random, quiz_wrong, quiz_recall,
    show_vocab, show_stats

Future hooks are marked TODO.
"""
from __future__ import annotations

import json, random, uuid, hashlib
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from collections import Counter

try:
    from gtts import gTTS
    from IPython.display import Audio, display
except ImportError:  # allow import without Colab
    gTTS, Audio, display = None, None, print

# ---------------------------------------------------------------------------
# Global constants – BASE is user‑configurable after import
# ---------------------------------------------------------------------------
BASE: Path = Path('.')            # to be overwritten in notebook
DATA_DIR: Path = Path('data')     # BASE / data
AUDIO_WORD_DIR: Path = Path('')   # BASE / data / audio_cache / words_audio
AUDIO_EX_DIR: Path = Path('')     # BASE / data / audio_cache / examples_audio
DB_FILE: Path = Path('')          # BASE / data / words.json
LOG_FILE: Path = Path('')         # BASE / data / quizzes.jsonl

# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def setup_dirs() -> None:
    """Create BASE/data/... structure and bind global paths."""
    global DATA_DIR, AUDIO_WORD_DIR, AUDIO_EX_DIR, DB_FILE, LOG_FILE
    DATA_DIR = BASE / 'data'
    AUDIO_WORD_DIR = DATA_DIR / 'audio_cache' / 'words_audio'
    AUDIO_EX_DIR = DATA_DIR / 'audio_cache' / 'examples_audio'
    for p in [DATA_DIR, AUDIO_WORD_DIR, AUDIO_EX_DIR]:
        p.mkdir(parents=True, exist_ok=True)
    DB_FILE = DATA_DIR / 'words.json'
    LOG_FILE = DATA_DIR / 'quizzes.jsonl'
    if not DB_FILE.exists():
        DB_FILE.write_text('{}', encoding='utf-8')


def load_db() -> Dict[str, Any]:
    return json.loads(DB_FILE.read_text(encoding='utf-8'))


def save_db(db: Dict[str, Any]) -> None:
    DB_FILE.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding='utf-8')

# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------

def _word_mp3_path(word: str) -> Path:
    return AUDIO_WORD_DIR / f"{word.lower()}.mp3"


def _ensure_word_audio(word: str) -> None:
    path = _word_mp3_path(word)
    if path.exists():
        return
    if gTTS is None:
        return
    tts = gTTS(word)
    tts.save(str(path))


def _play(path: Path):
    if Audio and path.exists():
        display(Audio(str(path), autoplay=True))


def _tts_sentence(text: str):
    if gTTS is None:
        return
    h = hashlib.md5(text.encode()).hexdigest()
    path = AUDIO_EX_DIR / f"{h}.mp3"
    if not path.exists():
        gTTS(text).save(str(path))
    _play(path)

# ---------------------------------------------------------------------------
# Core CRUD operations
# ---------------------------------------------------------------------------

def add_word(word: str, definition_en: str, examples: List[str] | None = None, tags: List[str] | None = None):
    """Insert or update a word entry; cache its audio."""
    db = load_db()
    entry = db.get(word, {
        'definition_en': '',
        'examples': [],
        'tags': [],
        'correct_cnt': 0,
        'wrong_cnt': 0,
        'added_at': datetime.utcnow().isoformat()
    })
    entry['definition_en'] = definition_en
    if examples:
        entry['examples'] = examples
    if tags:
        entry['tags'] = tags
    db[word] = entry
    save_db(db)
    _ensure_word_audio(word)


def search_word(word: str) -> Optional[Dict[str, Any]]:
    """Return word dict or None; pretty‑print if run in notebook."""
    db = load_db()
    entry = db.get(word)
    if entry:
        display({word: entry}) if 'display' in globals() else print({word: entry})
    return entry


def edit_word(word: str, *, definition_en: str | None = None,
              examples: List[str] | None = None, tags: List[str] | None = None):
    db = load_db()
    if word not in db:
        raise KeyError(f"'{word}' not found")
    if definition_en is not None:
        db[word]['definition_en'] = definition_en
    if examples is not None:
        db[word]['examples'] = examples
    if tags is not None:
        db[word]['tags'] = tags
    save_db(db)


def delete_word(word: str, *, purge_audio: bool = False):
    db = load_db()
    if word in db:
        db.pop(word)
        save_db(db)
        if purge_audio:
            _word_mp3_path(word).unlink(missing_ok=True)

# ---------------------------------------------------------------------------
# Quiz utilities
# ---------------------------------------------------------------------------

def _weighted_choice(words: List[str], db: Dict[str, Any]) -> str:
    weights = [db[w]['wrong_cnt'] + 1 for w in words]
    return random.choices(words, weights=weights, k=1)[0]


def _get_choices(target: str, db: Dict[str, Any]) -> List[str]:
    """Return list of 4 definitions (first is target) shuffled."""
    others = [w for w in db if w != target]
    random.shuffle(others)
    defs = [db[target]['definition_en']] + [db[o]['definition_en'] for o in others[:3]]
    random.shuffle(defs)
    return defs


def _ask_mcq(word: str, db: Dict[str, Any]):
    _play(_word_mp3_path(word))
    choices = _get_choices(word, db)
    print(f"\n⚙️  What is the meaning of '{word}'?")
    for i, c in enumerate(choices, 1):
        print(f"  {i}. {c}")
    ans = input('> ').strip()
    correct = choices[int(ans)-1] == db[word]['definition_en'] if ans.isdigit() else False
    if correct:
        print('✅ Correct!')
        db[word]['correct_cnt'] += 1
    else:
        print(f"❌ Wrong. → {db[word]['definition_en']}")
        db[word]['wrong_cnt'] += 1
    return correct


def quiz_random(n: int = 10):
    """Multiple‑choice quiz with *unique* words sampled by wrong_cnt weight."""
    db = load_db()
    if not db:
        print('No words in DB.')
        return
    pool = list(db.keys())
    n = min(n, len(pool))
    # sample without replacement by iterative weighted draw
    selected = []
    tmp_pool = pool.copy()
    for _ in range(n):
        choice = _weighted_choice(tmp_pool, db)
        selected.append(choice)
        tmp_pool.remove(choice)
    _run_session(selected, db, mode='random')


def quiz_wrong(n: int = 10):
    db = load_db()
    wrong_words = [w for w, e in db.items() if e['wrong_cnt'] > 0]
    if not wrong_words:
        print('No wrong words yet – great!')
        return
    n = min(n, len(wrong_words))
    selected = random.sample(wrong_words, k=n)
    _run_session(selected, db, mode='wrong_only')


def quiz_recall(n: int = 10):
    """Show definition, user types word."""
    db = load_db()
    pool = list(db.keys())
    n = min(n, len(pool))
    selected = random.sample(pool, k=n)
    correct_cnt = 0
    for word in selected:
        definition = db[word]['definition_en']
        print(f"\n💡 Word? → {definition}")
        ans = input('> ').strip()
        if ans.lower() == word.lower():
            print('✅')
            db[word]['correct_cnt'] += 1
            correct_cnt += 1
        else:
            print(f"❌ {word}")
            db[word]['wrong_cnt'] += 1
    _log_session(n, correct_cnt, mode='recall')
    save_db(db)
    print(f"Accuracy: {correct_cnt}/{n} = {correct_cnt/n*100:.1f}%")

# ---------------------------------------------------------------------------
# Session logging & helpers
# ---------------------------------------------------------------------------

def _run_session(words: List[str], db: Dict[str, Any], mode: str):
    correct_total = 0
    for w in words:
        if _ask_mcq(w, db):
            correct_total += 1
    _log_session(len(words), correct_total, mode)
    save_db(db)
    print(f"\nSession complete – Accuracy: {correct_total}/{len(words)} = {correct_total/len(words)*100:.1f}%")


def _log_session(q_cnt: int, correct: int, mode: str):
    entry = {
        'date': datetime.utcnow().isoformat(),
        'mode': mode,
        'questions': q_cnt,
        'correct': correct
    }
    with LOG_FILE.open('a', encoding='utf-8') as f:
        f.write(json.dumps(entry) + '\n')

# ---------------------------------------------------------------------------
# Reporting utilities
# ---------------------------------------------------------------------------

def show_vocab(order: str = 'alpha'):
    db = load_db()
    if not db:
        print('DB empty.')
        return
    if order == 'wrong_desc':
        words = sorted(db, key=lambda w: db[w]['wrong_cnt'], reverse=True)
    else:
        words = sorted(db)
    print(f"{'WORD':<20} {'WRONG':>5} {'CORRECT':>7}  TAGS")
    for w in words:
        e = db[w]
        print(f"{w:<20} {e['wrong_cnt']:>5} {e['correct_cnt']:>7}  {','.join(e['tags'])}")


def show_stats():
    db = load_db()
    total_attempts = sum(e['wrong_cnt']+e['correct_cnt'] for e in db.values())
    if total_attempts == 0:
        print('No attempts recorded yet.')
        return
    wrong_sum = sum(e['wrong_cnt'] for e in db.values())
    acc = 100*(total_attempts-wrong_sum)/total_attempts
    top_wrong = Counter({w:e['wrong_cnt'] for w,e in db.items()}).most_common(5)
    print(f"Total attempts: {total_attempts}, Accuracy: {acc:.1f}%")
    print('Top wrong words:')
    for w, c in top_wrong:
        print(f"  {w}: {c} errors")

# ---------------------------------------------------------------------------
# END
# ---------------------------------------------------------------------------

