# Word_learning/vocab.py

import json
from typing import List, Optional

from .core import load_db, save_db, now_iso
from .utils import speak

def add_word(word: str, definition_en: str, examples: List[str], tags: List[str]):
    db = load_db()
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
            'added_at': now_iso()
        }
    save_db(db)
    speak(word)

def speak_example(word: str, idx: int | None = None):
    """
    저장된 예문을 보여주고 TTS로 읽어 줍니다.
    • idx 가 None → 예문 목록만 표시
    • idx 지정 → 해당 예문 출력 + 음성 재생
    """
    db = load_db()
    rec = db.get(word)
    if not rec:
        print("Not found"); return

    examples = rec.get("examples", [])
    if not examples:
        print("No examples stored."); return

    if idx is None:
        for i, ex in enumerate(examples):
            print(f"[{i}] {ex}")
        return

    if idx < 0 or idx >= len(examples):
        print("Index out of range"); return

    ex = examples[idx]
    print(ex)
    speak(ex)

def show_vocab(order: str = 'alpha'):
    db = load_db()
    items = list(db.items())
    if order == 'wrong_desc':
        # 이전 에러를 방지하기 위해 .get()으로 안전하게 접근
        key_func = lambda t: t[1].get('stats', {}).get('choice', {}).get('w', 0) + \
                             t[1].get('stats', {}).get('spelling', {}).get('w', 0)
        items.sort(key=key_func, reverse=True)
    elif order == 'recent':
        items.sort(key=lambda t: t[1].get('added_at', ''), reverse=True)
    else: # 'alpha'
        items.sort()

    for w, d in items:
        s = d.get('stats', {})
        c = s.get('choice', {'c':0, 'w':0})
        sp = s.get('spelling', {'c':0, 'w':0})
        print(f"{w:15} choice {c['c']}/{c['w']} | spell {sp['c']}/{sp['w']}  {d['definition_en'][:60]}")

def search_word(word:str):
    db = load_db()
    if word in db:
        print(json.dumps(db[word], ensure_ascii=False, indent=2))
    else:
        print("Not found")

def delete_word(word:str):
    db = load_db()
    if word in db:
        del db[word]
        save_db(db)
        print(f"'{word}' has been deleted.")

def edit_word(word:str, definition_en:Optional[str]=None, tags:Optional[List[str]]=None):
    db = load_db()
    if word not in db:
        print("Not found"); return
    if definition_en:
        db[word]['definition_en'] = definition_en
    if tags is not None:
        db[word]['tags'] = tags
    save_db(db)
    print(f"'{word}' has been updated.")
