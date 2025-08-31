# Word_learning/quiz.py
"""
quiz.py
~~~~~~~
랜덤 객관식·오답 우선·스펠링(단어/문장) 퀴즈 + 세션 로그
- 문장(tags에 'sentence')은 첫글자 힌트 + Levenshtein 유사도 기준으로 관용 채점
"""

from __future__ import annotations

import json
import random
import sys
import time
import re
from typing import List

from . import core
from .utils import speak, levenshtein


# ──────────────────────────────────────────────────────────────────────────────
# 간단 헬퍼
# ──────────────────────────────────────────────────────────────────────────────

def _is_sentence(rec: dict) -> bool:
    """tags에 'sentence'가 있으면 문장으로 간주"""
    return "sentence" in set(rec.get("tags", []))

def _filter_by_tags(db: dict,
                    include: List[str] | None = None,
                    exclude: List[str] | None = None) -> list[str]:
    items = list(db.keys())
    if include:
        want = set(include)
        items = [w for w in items if want & set(db[w].get("tags", []))]
    if exclude:
        ban = set(exclude)
        items = [w for w in items if not (ban & set(db[w].get("tags", [])))]
    return items

def _first_letter_signature(text: str) -> str:
    """영숫자 단어들의 첫 글자를 이어붙인 서명"""
    words = re.findall(r"[A-Za-z0-9]+", text.lower())
    return "".join(w[0] for w in words if w)

def _mask_hint_first_letters(text: str) -> str:
    """단어별 첫 글자만 남기고 나머지는 '_'로 마스킹 (영문 단어만)"""
    def repl(m):
        w = m.group(0)
        return w[0] + "_" * (len(w) - 1) if len(w) > 1 else w
    return re.sub(r"[A-Za-z]+", repl, text)

def _lev_ratio(a: str, b: str) -> float:
    """Levenshtein 유사도 (0.0~1.0)"""
    a, b = a.strip().lower(), b.strip().lower()
    if not a and not b:
        return 1.0
    dist = levenshtein(a, b)
    return 1.0 - dist / max(len(a), len(b))

def _log_session(mode: str, total: int, correct: int, started: float) -> None:
    log = {
        "mode": mode,
        "total": total,
        "correct": correct,
        "acc": round(correct / total * 100, 1) if total else 0.0,
        "started_at": core.now_iso(),
        "duration": round(time.time() - started, 1),
    }
    core.setup_dirs()
    log_file = core.DATA_DIR / "quizzes.jsonl"
    with log_file.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(log, ensure_ascii=False) + "\n")

def _stats(rec: dict, key: str) -> dict:
    """stats[key]를 c/w 기본값과 함께 보장"""
    return rec.setdefault("stats", {}).setdefault(key, {"c": 0, "w": 0})

def _stats_tuple(rec: dict, key: str) -> tuple[int, int, int, float]:
    """(c, w, tot, err_rate)"""
    st = _stats(rec, key)
    c, w = st.get("c", 0), st.get("w", 0)
    tot = c + w
    err = (w / tot) if tot else 1.0
    return c, w, tot, err

def _stats_str(rec) -> str:
    """choice (c/w) 와 spelling (c/w) 를 'choice 3/1 | spell 2/0' 형태로 반환"""
    ch = rec.get("stats", {}).get("choice", {})
    sp = rec.get("stats", {}).get("spelling", {})
    return (f"choice {ch.get('c',0)}/{ch.get('w',0)} | "
            f"spell {sp.get('c',0)}/{sp.get('w',0)}")


# ──────────────────────────────────────────────────────────────────────────────
# 출제 대상 선정
# ──────────────────────────────────────────────────────────────────────────────

def _pick_items_for_choice(db: dict, n: int,
                           include_tags: List[str] | None = None,
                           exclude_tags: List[str] | None = None,
                           require_def: bool = True) -> list[str]:
    items = _filter_by_tags(db, include=include_tags, exclude=exclude_tags)
    if require_def:
        items = [w for w in items if db[w].get("definition_en", "").strip()]
    items.sort(key=lambda w: (
        _stats_tuple(db[w], "choice")[2],     # tot asc
        -_stats_tuple(db[w], "choice")[1],    # wrong desc
    ))
    return items[: min(n, len(items))]

def _pick_items_for_wrong(db: dict, n: int,
                          include_tags: List[str] | None = None,
                          exclude_tags: List[str] | None = None,
                          require_def: bool = True) -> list[str]:
    cand = _filter_by_tags(db, include=include_tags, exclude=exclude_tags)
    pool = []
    for w in cand:
        rec = db[w]
        if require_def and not rec.get("definition_en", "").strip():
            continue
        c, wcnt, *_ = _stats_tuple(rec, "choice")
        if c < wcnt + 2:
            pool.append(w)
    pool.sort(key=lambda w: _stats_tuple(db[w], "choice")[1], reverse=True)
    return pool[: min(n, len(pool))]

def _pick_items_for_spelling(db: dict, n: int, strategy: str, tags: List[str] | None) -> list[str]:
    items = _filter_by_tags(db, include=tags, exclude=None)
    if not items:
        return []
    if strategy == "hard":
        items.sort(key=lambda w: (
            _stats_tuple(db[w], "spelling")[1],
            _stats_tuple(db[w], "spelling")[3],
            _stats_tuple(db[w], "spelling")[2],
        ), reverse=True)
    else:
        items.sort(key=lambda w: (
            _stats_tuple(db[w], "spelling")[2],
            -_stats_tuple(db[w], "spelling")[1],
        ))
    return items[: min(n, len(items))]


# ──────────────────────────────────────────────────────────────────────────────
# 공용 세션 러너
# ──────────────────────────────────────────────────────────────────────────────

def _multiple_choice_session(db: dict, words: list[str]) -> int:
    """객관식 세션 공용 러너 (random/wrong 공통)"""
    if not words:
        print("No words to quiz!")
        return 0

    all_defs = [rec.get("definition_en", "") for rec in db.values()]
    correct_cnt = 0

    for w in words:
        rec = db[w]
        speak(w, ui="js")
        time.sleep(0.12)

        correct_def = rec.get("definition_en", "")
        others = [d for d in all_defs if d and d != correct_def]
        # 최소 보기 2개 확보
        k = 3 if len(others) >= 3 else max(0, len(others))
        choices = [correct_def] + (random.sample(others, k=k) if k else [])
        random.shuffle(choices)
        correct_idx = choices.index(correct_def) if correct_def in choices else -1

        print("\nChoose the correct definition:")
        for i, d in enumerate(choices, 1):
            print(f" {i} {d[:120]}")
        sys.stdout.flush()

        sel = input("Your choice: ").strip()
        idx = int(sel) - 1 if sel.isdigit() else -1

        st = _stats(rec, "choice")

        if 0 <= idx < len(choices) and idx == correct_idx:
            st["c"] += 1
            correct_cnt += 1
            print(f"✔️ Correct  → {w}   [{_stats_str(rec)}]\n")
        else:
            st["w"] += 1
            ans = f" #{correct_idx+1}" if correct_idx >= 0 else ""
            print(f"❌ Wrong  → {w}{ans} “{correct_def}”   [{_stats_str(rec)}]\n")
            speak(w, ui="js")
            time.sleep(0.12) 

        # 예문 출력
        examples = rec.get("examples", [])
        if examples:
            print("Examples:")
            for ex in examples:
                print(f"  • {ex}")
            print()  # 공백줄

        print("*" * 30)

    return correct_cnt


# ──────────────────────────────────────────────────────────────────────────────
# public API
# ──────────────────────────────────────────────────────────────────────────────

def show_sessions(limit: int = 10) -> None:
    core.setup_dirs()
    f = core.DATA_DIR / "quizzes.jsonl"
    if not f.exists():
        print("(no sessions yet)")
        return

    lines = f.read_text(encoding="utf-8").strip().split("\n")[-limit:][::-1]
    for ln in lines:
        j = json.loads(ln)
        print(
            f"{j['mode']:8} | {j['total']:3} | {j['acc']:5}% "
            f"| {j['duration']:4}s | {j['started_at'][:16]}"
        )

def quiz_random(n: int = 10,
                include_tags: List[str] | None = None,
                exclude_tags: List[str] | None = ["sentence"]) -> None:
    db = core.load_db()
    words = _pick_items_for_choice(db, n, include_tags, exclude_tags, require_def=True)
    if not words:
        print("No eligible words (maybe all lack definitions or excluded by tags)."); return
    t0 = time.time()
    correct_cnt = _multiple_choice_session(db, words)
    core.save_db(db)
    print(f"Accuracy {correct_cnt}/{len(words)} ({round(correct_cnt/len(words)*100,1)}%)")
    _log_session("choice", len(words), correct_cnt, t0)

def quiz_wrong(n: int = 10,
               include_tags: List[str] | None = None,
               exclude_tags: List[str] | None = ["sentence"]) -> None:
    db = core.load_db()
    words = _pick_items_for_wrong(db, n, include_tags, exclude_tags, require_def=True)
    if not words:
        print("🎉 No wrong words left to review (or filtered out)."); return
    t0 = time.time()
    correct_cnt = _multiple_choice_session(db, words)
    core.save_db(db)
    print(f"Accuracy {correct_cnt}/{len(words)} ({round(correct_cnt/len(words)*100,1)}%)")
    _log_session("wrong", len(words), correct_cnt, t0)

def quiz_spelling(n: int = 10,
                  strategy: str = "least",
                  tags: List[str] | None = None,
                  sentence_threshold: float = 0.90) -> None:
    """
    스펠링 리콜 (단어/문장 포함)
    - 단어: 정확 일치만 정답, 1글자 차이는 안내만.
    - 문장(tags에 'sentence'): 첫글자 시그니처 일치 && 유사도≥threshold면 정답 처리.
    """
    db = core.load_db()
    words = _pick_items_for_spelling(db, n, strategy=strategy, tags=tags)
    if not words:
        print("No words to quiz!")
        return

    correct_cnt, t0 = 0, time.time()

    for w in words:
        rec = db[w]
        is_sent = _is_sentence(rec)

        # 문장 힌트
        print("\n" + "-" * 50)
        if is_sent:
            print("Sentence mode: type the full sentence you hear.")
            print(f"Hint (first letters): {_mask_hint_first_letters(w)}")

        # 오디오 & 입력
        speak(w, ui="js"); print(); sys.stdout.flush()
        time.sleep(0.12)
        prompt = "▶ Type what you heard (Enter = replay): " if is_sent \
                 else "▶ Type the word you heard (Enter = replay): "
        ans = input(prompt).strip()
        if ans == "":
            speak(w, ui="js"); print(); sys.stdout.flush()
            ans = input("> ").strip()

        st = _stats(rec, "spelling")

        if not is_sent:
            # 단어 채점
            dist = levenshtein(ans.lower(), w.lower())
            if dist == 0:
                print("✔️ Perfect\n"); st["c"] += 1; correct_cnt += 1
            elif dist == 1:
                print("➖ Almost (1 letter off) — counted as wrong\n"); st["w"] += 1
            else:
                print(f"❌ Wrong  → {w}\n"); st["w"] += 1
        else:
            # 문장 채점
            sig_ok = _first_letter_signature(ans) == _first_letter_signature(w)
            ratio = _lev_ratio(ans, w)
            if ans.strip().lower() == w.strip().lower():
                print("✔️ Perfect (exact match)\n"); st["c"] += 1; correct_cnt += 1
            elif sig_ok and ratio >= sentence_threshold:
                print(f"✔️ Good enough (≥{int(sentence_threshold*100)}%) — ratio={ratio:.2f}\n")
                st["c"] += 1; correct_cnt += 1
            else:
                print(f"❌ Wrong  →\nExpected: {w}\nYour   : {ans}\n"
                      f"(sig_ok={sig_ok}, ratio={ratio:.2f})\n")
                st["w"] += 1

        # 뜻/예문 출력
        if "definition_en" in rec:
            print(f"Definition: {rec['definition_en']}\n")
        examples = rec.get("examples", [])
        if examples:
            print("Examples:")
            for ex in examples:
                print(f"  • {ex}")
            print()

    core.save_db(db)
    acc = round(correct_cnt / len(words) * 100, 1)
    print(f"Spelling acc {correct_cnt}/{len(words)} ({acc}%)")
    _log_session("spelling", len(words), correct_cnt, t0)
