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
def _pick_words(db: dict, n: int, mode: str = "choice") -> list[str]:
    """
    mode == "choice"  → 정의 퀴즈(quiz_random, quiz_spelling): 
                         (correct+wrong) 횟수가 적은 단어 먼저
    mode == "wrong"   → 오답 퀴즈(quiz_wrong):
                         wrong 횟수가 많은 단어 먼저
    """
    # 모든 단어 키 리스트
    items = list(db.keys())
    if mode == "wrong":
        # 틀린 횟수 많은 순
        items.sort(key=lambda w: db[w]["stats"]["choice"]["wrong"], reverse=True)
    else:
        # 푼 횟수(정답+오답) 적은 순
        items.sort(key=lambda w: (
            db[w]["stats"]["choice"]["correct"] + db[w]["stats"]["choice"]["wrong"]
        ))
    return items[: min(n, len(items))]


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
    words = _pick_words(db, n, mode='choice')
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
        correct_idx = choices.index(correct_def)

        print("\nChoose the correct definition:")
        for i, d in enumerate(choices, 1):
            print(f" {i} {d[:120]}")
        sys.stdout.flush()

        sel = input("Your choice: ")
        idx = int(sel) - 1 if sel.isdigit() else -1

        # 통계 --------------------------------------------------------
        st = db[w].setdefault("stats", {}).setdefault("choice", {"c": 0, "w": 0})

        if 0 <= idx < len(choices) and choices[idx] == correct_def:
            print(f"✔️ Correct  → {w}\n")
            st["c"] += 1; correct_cnt += 1
        else:
            print(f"❌ Wrong  → {w} #{correct_idx+1} “{correct_def}”\n")
            speak(w)              # 정답 발음 재생
            st["w"] += 1

    core.save_db(db)
    print(f"Accuracy {correct_cnt}/{len(words)} "
          f"({round(correct_cnt/len(words)*100,1)}%)")
    _log_session("choice", len(words), correct_cnt, t0)

def quiz_wrong(n: int = 10) -> None:
    """
    '틀린 횟수 - 맞힌 횟수 >= 0' 인 단어만 출제.
    해당 단어가 리스트에서 사라지려면
    ① 맞힌 횟수(c) 가 틀린 횟수(w) 보다 **2 이상 많아져야** 합니다.
       (조건: c >= w + 2)
    """
    db = core.load_db()

    def is_still_wrong(rec):
        st = rec.get("stats", {}).get("choice", {})
        c, w = st.get("c", 0), st.get("w", 0)
        return c < w + 2          # 아직 졸업 못함

    pool = [w for w, rec in db.items() if is_still_wrong(rec)]
    if not pool:
        print("🎉 No wrong words left to review!")
        return

    words = _pick_words({w: db[w] for w in pool}, n, mode="wrong")
    # 이하 로직은 quiz_random() 과 동일 --------------------------------
    all_defs = [rec["definition_en"] for rec in db.values()]
    correct_cnt, t0 = 0, time.time()

    for w in words:
        speak(w)
        correct_def = db[w]["definition_en"]
        others = [d for d in all_defs if d != correct_def]
        choices = [correct_def] + random.sample(others, k=min(3, len(others)))
        random.shuffle(choices)
        correct_idx = choices.index(correct_def)

        print("\nChoose the correct definition:")
        for i, d in enumerate(choices, 1):
            print(f" {i} {d[:120]}")
        sys.stdout.flush()

        sel = input("Your choice: ")
        idx = int(sel) - 1 if sel.isdigit() else -1
        st = db[w].setdefault("stats", {}).setdefault("choice", {"c": 0, "w": 0})

        if 0 <= idx < len(choices) and choices[idx] == correct_def:
            print(f"✔️ Correct  → {w}\n")
            st["c"] += 1; correct_cnt += 1
        else:
            print(f"❌ Wrong  → {w} #{correct_idx+1} “{correct_def}”\n")
            speak(w)              # 정답 발음 재생
            st["w"] += 1

    core.save_db(db)
    print(f"Accuracy {correct_cnt}/{len(words)} "
          f"({round(correct_cnt/len(words)*100,1)}%)")
    _log_session("wrong", len(words), correct_cnt, t0)


def quiz_spelling(n: int = 10):
    db = core.load_db()
    words = _pick_words(db, n, mode="choice")
    if not words:
        print("No words to quiz!"); return

    correct_cnt, t0 = 0, time.time()
    for w in words:
        speak(w)                         # 오디오 위젯 출력
        print("\n" * 2)                  # ➊ 입력창이 위젯 아래로 내려오도록 빈 줄 삽입
        print("▶ Type the word you heard (hit Enter twice to replay):")
        ans = input().strip()
        if ans == "":                    # ➌ 빈 입력이면 다시 재생해 준다
            speak(w); print("\n" * 2); sys.stdout.flush()
            ans = input("▶ Type again: ").strip()

        dist = levenshtein(ans.lower(), w.lower())
        st = db[w].setdefault("stats", {}).setdefault("spelling", {"c":0,"w":0})

        if dist == 0:
            print("✔️ Perfect\n"); st["c"] += 1; correct_cnt += 1
        elif dist == 1:
            print(f"➖ Almost (1 letter off) → {w}\n"); st["w"] += 1
        else:
            print(f"❌ Wrong → {w}\n"); st["w"] += 1

    core.save_db(db)
    print(f"Spelling acc {correct_cnt}/{len(words)} "
          f"({round(correct_cnt/len(words)*100,1)}%)")
    _log_session("spelling", len(words), correct_cnt, t0)
