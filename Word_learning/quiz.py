# Word_learning/quiz.py
"""
quiz.py
~~~~~~~
랜덤 객관식·스펠링 퀴즈 + 세션 로그
"""

from __future__ import annotations

import json
import random
import sys
import time
from typing import List

from . import core
from .utils import speak, levenshtein

# ------------------------------------------------------------------
# 내부 헬퍼
# ------------------------------------------------------------------
def _pick_words(db: dict, n: int) -> List[str]:
    words = list(db.keys())
    return words if len(words) <= n else random.sample(words, n)


def _log_session(mode: str, total: int, correct: int, started: float) -> None:
    log = {
        "mode": mode,
        "total": total,
        "correct": correct,
        "acc": round(correct / total * 100, 1) if total else 0.0,
        "started_at": core.now_iso(),
        "duration": round(time.time() - started, 1),
    }
    core.setup_dirs()          # DATA_DIR 보장
    log_file = core.DATA_DIR / "quizzes.jsonl"
    with log_file.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(log, ensure_ascii=False) + "\n")


# ------------------------------------------------------------------
# public API
# ------------------------------------------------------------------
def show_sessions(limit: int = 10) -> None:
    core.setup_dirs()          # 파일 존재 보장
    f = core.DATA_DIR / "quizzes.jsonl"
    if not f.exists():
        print("(no sessions yet)"); return

    lines = f.read_text(encoding="utf-8").strip().split("\n")[-limit:][::-1]
    for ln in lines:
        j = json.loads(ln)
        print(
            f"{j['mode']:8} | {j['total']:3} | {j['acc']:5}% "
            f"| {j['duration']:4}s | {j['started_at'][:16]}"
        )


def quiz_random(n: int = 10) -> None:
    db = core.load_db()
    words = _pick_words(db, n)
    if not words:
        print("No words to quiz!"); return

    all_defs = [d["definition_en"] for d in db.values()]
    correct_cnt, t0 = 0, time.time()

    for w in words:
        speak(w)
        correct_def = db[w]["definition_en"]

        # 보기 구성 ---------------------------------------------------
        others = [d for d in all_defs if d != correct_def]
        choices = [correct_def] + random.sample(others, k=min(3, len(others)))
        random.shuffle(choices)

        print("\nChoose the correct definition:")
        for i, d in enumerate(choices, 1):
            print(f" {i} {d[:80]}")
        sys.stdout.flush()

        sel = input("Your choice: ")
        idx = int(sel) - 1 if sel.isdigit() else -1

        # 통계 --------------------------------------------------------
        st = db[w].setdefault("stats", {}).setdefault("choice", {"c": 0, "w": 0})

        if 0 <= idx < len(choices) and choices[idx] == correct_def:
            print("✔️ Correct\n")
            st["c"] += 1
            correct_cnt += 1
        else:
            print(f"❌ Wrong  → {w}\n")
            st["w"] += 1

    core.save_db(db)
    print(f"Accuracy {correct_cnt}/{len(words)} "
          f"({round(correct_cnt/len(words)*100,1)}%)")
    _log_session("choice", len(words), correct_cnt, t0)


def quiz_spelling(n: int = 10) -> None:
    db = core.load_db()
    words = _pick_words(db, n)
    if not words:
        print("No words to quiz!"); return

    correct_cnt, t0 = 0, time.time()

    for w in words:
        speak(w)
        sys.stdout.flush()
        ans = input("▶ Type the word you heard: ").strip()
        dist = levenshtein(ans.lower(), w.lower())

        st = db[w].setdefault("stats", {}).setdefault("spelling", {"c": 0, "w": 0})

        if dist == 0:
            print("✔️ Perfect\n")
            st["c"] += 1
            correct_cnt += 1
        elif dist == 1:
            print(f"➖ Almost (1 letter off) → {w}\n")
            st["w"] += 1
        else:
            print(f"❌ Wrong → {w}\n")
            st["w"] += 1

    core.save_db(db)
    print(f"Spelling acc {correct_cnt}/{len(words)} "
          f"({round(correct_cnt/len(words)*100,1)}%)")
    _log_session("spelling", len(words), correct_cnt, t0)
