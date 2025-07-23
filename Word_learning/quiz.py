# Word_learning/quiz.py

import random, time, json, sys

from .core import load_db, save_db, DATA_DIR, now_iso
from .utils import speak, levenshtein

def _pick_words(db: dict, n: int) -> List[str]:
    words = list(db.keys())
    return words if len(words) <= n else random.sample(words, n)

def _log_session(mode: str, total: int, correct: int, t0: float):
    log = {
        'mode': mode, 'total': total, 'correct': correct,
        'acc': round(correct / total * 100, 1) if total > 0 else 0,
        'started_at': now_iso(),
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

def quiz_random(n: int = 10):
    db = load_db(); words = _pick_words(db, n)
    if not words: print("No words to quiz!"); return
    correct, t0 = 0, time.time()

    all_defs = [d['definition_en'] for d in db.values()]

    for w in words:
        speak(w)
        correct_def = db[w]['definition_en']
        defs = {correct_def}
        
        # 자신을 제외한 나머지 정의들
        other_defs = [d for d in all_defs if d != correct_def]
        
        # 3개의 보기 추가
        k = min(3, len(other_defs))
        defs.update(random.sample(other_defs, k=k))

        shuffled_defs = random.sample(list(defs), len(defs))

        print("\nChoose the correct definition for the word you heard:")
        for i, d in enumerate(shuffled_defs, 1):
            print(f" {i} {d[:80]}")

        sys.stdout.flush()
        choice = input("Your choice: ")
        idx = int(choice) - 1 if choice.isdigit() else -1

        stats = db[w].setdefault('stats', {})
        choice_stats = stats.setdefault('choice', {})

        if 0 <= idx < len(shuffled_defs) and shuffled_defs[idx] == correct_def:
            print("✔️ Correct\n"); correct +=1
            choice_stats['c'] = choice_stats.get('c', 0) + 1
        else:
            print(f"❌ Wrong  → {w}\n")
            choice_stats['w'] = choice_stats.get('w', 0) + 1
    
    save_db(db)
    print(f"Accuracy {correct}/{len(words)} ({round(correct/len(words)*100,1)}%)")
    _log_session('choice', len(words), correct, t0)


def quiz_spelling(n: int = 10):
    db = load_db(); words = _pick_words(db, n)
    if not words: print("No words to quiz!"); return
    correct, t0 = 0, time.time()
    
    for w in words:
        speak(w)
        sys.stdout.flush()
        ans = input("▶ Type the word you heard: ").strip()
        dist = levenshtein(ans.lower(), w.lower())

        stats = db[w].setdefault('stats', {})
        spelling_stats = stats.setdefault('spelling', {})

        if dist == 0:
            print("✔️ Perfect\n"); correct +=1
            spelling_stats['c'] = spelling_stats.get('c', 0) + 1
        elif dist == 1:
            print(f"➖ Almost (1 letter off) → {w}\n")
            spelling_stats['w'] = spelling_stats.get('w', 0) + 1
        else:
            print(f"❌ Wrong → {w}\n")
            spelling_stats['w'] = spelling_stats.get('w', 0) + 1
            
    save_db(db)
    print(f"Spelling acc {correct}/{len(words)} ({round(correct/len(words)*100,1)}%)")
    _log_session('spelling', len(words), correct, t0)
