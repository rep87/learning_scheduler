# -*- coding: utf-8 -*-
"""
Word‑Learning Scheduler (MVP v0.1)
=================================
Single‑file package importable from Colab.

Core phase‑1 features implemented:
    • Persist word DB (JSON) with per‑word stats & tags
    • Cache TTS audio for *words* on insertion (gTTS → mp3)
    • Optional on‑demand TTS for example sentences
    • Two quiz modes: random() and wrong_only()
    • Basic recall (type‑in) mode   (quiz_recall)
    • Simple SRS‑friendly weight formula (wrong_cnt+1)/(correct_cnt+1)
    • Session logging + rudimentary stats

Future hooks marked TODO for: SM‑2 scheduling, STT pronunciation check, multi‑lang definitions.
"""
from __future__ import annotations
import json, random, hashlib, uuid, datetime as _dt
from pathlib import Path
from typing import List, Dict, Any

try:
    from gtts import gTTS
    from IPython.display import Audio, display
except ImportError:  # graceful degradation
    gTTS = None
    Audio = None
    def display(x):
        print("[display]", x)

# ----------------------- configurable base path -------------------------
BASE: Path = Path("./learning_scheduler")

# ----------------------- internal helpers ------------------------------

def _paths() -> Dict[str, Path]:
    data = BASE / "data"
    audio_words = data / "audio_cache" / "words_audio"
    audio_examples = data / "audio_cache" / "examples_audio"
    return {
        "data": data,
        "words_json": data / "words.json",
        "quiz_log": data / "quizzes.jsonl",
        "audio_words": audio_words,
        "audio_examples": audio_examples,
    }


def setup_dirs() -> None:
    """Create required directories if absent."""
    for p in _paths().values():
        if p.suffix:  # skip files
            continue
        p.mkdir(parents=True, exist_ok=True)


# ----------------------- DB I/O ----------------------------------------

def _load_db() -> Dict[str, Any]:
    fp = _paths()["words_json"]
    if not fp.exists():
        return {}
    with fp.open("r", encoding="utf‑8") as f:
        return json.load(f)


def _save_db(db: Dict[str, Any]) -> None:
    fp = _paths()["words_json"]
    with fp.open("w", encoding="utf‑8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)


# ----------------------- TTS utilities ---------------------------------

def _tts_to_mp3(text: str, out_path: Path):
    if gTTS is None:
        return  # gTTS not available → skip audio
    out_path.parent.mkdir(parents=True, exist_ok=True)
    gTTS(text=text, lang="en").save(str(out_path))


def _ensure_word_audio_cached(word: str):
    audio_path = _paths()["audio_words"] / f"{word.lower()}.mp3"
    if not audio_path.exists():
        _tts_to_mp3(word, audio_path)
    if Audio and audio_path.exists():
        display(Audio(str(audio_path), autoplay=True))


def _example_audio(text: str):
    h = hashlib.md5(text.encode()).hexdigest()[:10]
    audio_path = _paths()["audio_examples"] / f"{h}.mp3"
    if not audio_path.exists():
        _tts_to_mp3(text, audio_path)
    if Audio and audio_path.exists():
        display(Audio(str(audio_path), autoplay=True))


# ----------------------- Public API ------------------------------------

def add_word(*, word: str, definition_en: str, examples: List[str] | None = None,
             tags: List[str] | None = None):
    """Insert or update a word entry and cache its TTS audio."""
    setup_dirs()
    db = _load_db()
    wkey = word.lower()
    entry = db.get(wkey, {
        "word": wkey,
        "definition_en": definition_en,
        "examples": examples or [],
        "tags": tags or [],
        "correct_cnt": 0,
        "wrong_cnt": 0,
        "added": _dt.date.today().isoformat(),
    })
    # update
    entry["definition_en"] = definition_en
    if examples:
        entry.setdefault("examples", []).extend(examples)
    if tags:
        entry.setdefault("tags", []).extend([t for t in tags if t not in entry["tags"]])
    db[wkey] = entry
    _save_db(db)
    _ensure_word_audio_cached(wkey)


# ----------------------- quiz internals --------------------------------

def _weighted_sample(words: List[Dict[str, Any]], k: int) -> List[Dict[str, Any]]:
    weights = []
    for e in words:
        w = (e["wrong_cnt"] + 1) / (e["correct_cnt"] + 1)
        weights.append(w)
    return random.choices(words, weights=weights, k=min(k, len(words)))


def _choice_defs(db: Dict[str, Any], target_key: str, n_choices: int = 4):
    all_keys = list(db.keys())
    all_keys.remove(target_key)
    distractors = random.sample(all_keys, k=min(n_choices - 1, len(all_keys)))
    options = [db[target_key]["definition_en"]] + [db[k]["definition_en"] for k in distractors]
    random.shuffle(options)
    return options


def _log_session(total_q: int, correct: int):
    log_path = _paths()["quiz_log"]
    with log_path.open("a", encoding="utf‑8") as f:
        f.write(json.dumps({
            "timestamp": _dt.datetime.now().isoformat(),
            "total": total_q,
            "correct": correct,
        }) + "\n")


# ----------------------- Quiz modes ------------------------------------

def quiz_random(n: int = 10):
    """4‑choice quiz drawn from all vocabulary."""
    _quiz_core(n, mode="all")


def quiz_wrong(n: int = 10):
    """Quiz prioritising words answered wrong at least once."""
    _quiz_core(n, mode="wrong_only")


def quiz_recall(n: int = 10):
    """Recall (type‑in) quiz."""
    _quiz_core(n, mode="recall")


def _quiz_core(n: int, mode: str):
    db = _load_db()
    if not db:
        print("[!] Vocabulary empty – add words first.")
        return
    words_pool = list(db.values()) if mode != "wrong_only" else [e for e in db.values() if e["wrong_cnt"] > 0]
    if not words_pool:
        print("[!] No words meet the selection criteria.")
        return
    selected = _weighted_sample(words_pool, n)
    correct_total = 0
    for idx, entry in enumerate(selected, 1):
        key = entry["word"]
        print(f"\nQ{idx}/{len(selected)} — {key}")
        _ensure_word_audio_cached(key)
        if mode == "recall":
            ans = input("Type the English definition: \n> ")
            is_correct = ans.strip().lower() == entry["definition_en"].lower()
        else:
            choices = _choice_defs(db, key)
            for i, c in enumerate(choices, 1):
                print(f"  {i}. {c}")
            try:
                sel = int(input("Your choice (1‑4): ").strip())
            except ValueError:
                sel = 0
            is_correct = 1 <= sel <= len(choices) and choices[sel - 1] == entry["definition_en"]
        print("✅ Correct!" if is_correct else f"❌ Wrong – {entry['definition_en']}")
        if not is_correct and entry["examples"]:
            ex = random.choice(entry["examples"])
            print("   ex:", ex)
            _example_audio(ex)
        entry["correct_cnt" if is_correct else "wrong_cnt"] += 1
        correct_total += int(is_correct)
    _save_db(db)
    print(f"\n=== Session result: {correct_total}/{len(selected)} ({correct_total/len(selected)*100:.1f}%) ===")
    _log_session(len(selected), correct_total)


# ----------------------- simple views ----------------------------------

def show_vocab(order: str = "word"):
    db = _load_db()
    if not db:
        print("[!] No vocabulary yet.")
        return
    rows = list(db.values())
    if order == "wrong_desc":
        rows.sort(key=lambda x: x["wrong_cnt"], reverse=True)
    elif order == "recent":
        rows.sort(key=lambda x: x["added"], reverse=True)
    else:
        rows.sort(key=lambda x: x["word"])
    print(f"Vocab size: {len(rows)}\nword | correct | wrong | tags")
    for e in rows:
        print(f"{e['word']:<15} {e['correct_cnt']:<3} {e['wrong_cnt']:<3} {','.join(e['tags'])}")


def show_stats():
    """Aggregate stats from quiz log."""
    log_path = _paths()["quiz_log"]
    if not log_path.exists():
        print("[!] No quiz sessions logged yet.")
        return
    sessions = [json.loads(l) for l in log_path.read_text().strip().splitlines() if l]
    total = sum(s["total"] for s in sessions)
    correct = sum(s["correct"] for s in sessions)
    if total:
        print(f"Overall accuracy: {correct}/{total} ({correct/total*100:.1f}%) across {len(sessions)} sessions")
    else:
        print("No questions answered yet.")


# ----------------------- command‑line entrypoint -----------------------
if __name__ == "__main__":
    import argparse, sys as _sys
    parser = argparse.ArgumentParser(description="Word Learning Scheduler – CLI helper")
    parser.add_argument("mode", choices=["random", "wrong", "recall", "stats", "vocab"], help="run mode")
    parser.add_argument("-n", type=int, default=10, help="number of questions")
    args = parser.parse_args()
    if args.mode == "random":
        quiz_random(args.n)
    elif args.mode == "wrong":
        quiz_wrong(args.n)
    elif args.mode == "recall":
        quiz_recall(args.n)
    elif args.mode == "stats":
        show_stats()
    elif args.mode == "vocab":
        show_vocab("wrong_desc")
    else:
        _sys.exit("Unknown mode")
