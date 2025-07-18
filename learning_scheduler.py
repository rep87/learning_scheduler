# learning_scheduler.py  ── URKCE + TAG
# ================================================================
# • LearningItem.tags  (List[str])
# • add_item(..., tags=[...])
# • get_due_items(..., tag_filter=[...])
# • review_item()  : 동그라미 3회 → completed 이동
# • 새 옵션 --fix-untagged : 태그가 없는 모든 항목을 한 번에 보정
# ================================================================
from __future__ import annotations

import json, uuid, argparse, sys
from dataclasses import dataclass, asdict, field
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional

# -----------------------------------------------------------------
ACTIVE_PATH = Path("learning_items.json")
DONE_PATH   = Path("completed_items.json")
INTERVALS   = {0: 1, 1: 3, 2: 7, 3: 30}     # 기억 카운트별 간격(days)
# -----------------------------------------------------------------

# --------------------------- 데이터 모델 --------------------------
@dataclass
class LearningItem:
    content: str
    summary: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    initial_date: str = field(default_factory=lambda: date.today().isoformat())
    last_review_date: str = field(default_factory=lambda: date.today().isoformat())
    next_review_date: str = field(default_factory=lambda: (date.today()+timedelta(days=1)).isoformat())
    memory_count: int = 0
    status: str = "X"          # "O" "Δ" "X"
    history: List[dict] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)   # ★

    # ------------- 상태 업데이트 --------------
    def review(self, status: str, summary_update: Optional[str] = None,
               add_tags: Optional[List[str]] = None):
        status = status.upper()
        if status not in {"O", "Δ", "X"}:
            raise ValueError("status must be O, Δ, or X")

        today = date.today().isoformat()
        self.status = status
        self.last_review_date = today
        self.history.append({"date": today, "status": status})

        if summary_update is not None:
            self.summary = summary_update
        if add_tags:
            # 중복 없이 병합
            self.tags = list({*self.tags, *add_tags})

        if status == "O":
            self.memory_count = min(self.memory_count + 1, 3)
        elif status == "X":
            self.memory_count = 0

        self.next_review_date = (
            date.today() + timedelta(days=INTERVALS[self.memory_count])
        ).isoformat()

    # ------------- 헬퍼 --------------
    def is_due(self, on: date) -> bool:
        return date.fromisoformat(self.next_review_date) <= on

    def to_dict(self): return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "LearningItem":
        if "tags" not in d:          # 과거 JSON 호환
            d["tags"] = []
        return LearningItem(**d)

# --------------------------- DB 래퍼 ------------------------------
class LearningDB:
    def __init__(self,
                 active_path: Path = ACTIVE_PATH,
                 done_path: Path = DONE_PATH):
        self.active_path   = active_path
        self.done_path     = done_path
        self.active: List[LearningItem]   = []
        self.completed: List[LearningItem] = []
        self.load()

    # ---------- IO ----------
    def load(self):
        self.active    = self._load_file(self.active_path)
        self.completed = self._load_file(self.done_path)

    def save(self):
        self._save_file(self.active_path,   self.active)
        self._save_file(self.done_path,     self.completed)

    def _load_file(self, path: Path) -> List[LearningItem]:
        if not path.exists(): return []
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        return [LearningItem.from_dict(x) for x in raw]

    def _save_file(self, path: Path, items: List[LearningItem]):
        with path.open("w", encoding="utf-8") as f:
            json.dump([it.to_dict() for it in items],
                      f, ensure_ascii=False, indent=2)

    # ---------- CRUD ----------
    def add_item(self, content: str, summary: str = "",
                 tags: Optional[List[str]] = None) -> LearningItem:
        it = LearningItem(content=content,
                          summary=summary,
                          tags=tags or [])
        self.active.append(it)
        self.save()
        return it

    def delete_item(self, item_id: str, completed=False) -> bool:
        lst = self.completed if completed else self.active
        for it in lst:
            if it.id.startswith(item_id):
                lst.remove(it)
                self.save()
                return True
        return False

    # ---------- 쿼리 ----------
    def get_due_items(self,
                      on: date = date.today(),
                      tag_filter: Optional[List[str]] = None) -> List[LearningItem]:
        pool = [it for it in self.active if it.is_due(on)]
        if tag_filter:
            wanted = {t.lower() for t in tag_filter}
            pool = [
                it for it in pool
                if wanted & {t.lower() for t in it.tags}
            ]
        pool.sort(key=lambda x: (
            date.fromisoformat(x.next_review_date),
            x.memory_count,
            x.status == "X",
        ))
        return pool

    # ---------- 리뷰 ----------
    def review_item(self, item: LearningItem, status: str,
                    summary_update: Optional[str] = None,
                    add_tags: Optional[List[str]] = None):
        item.review(status, summary_update, add_tags)
        if item.memory_count >= 3 and status == "O":
            self.active.remove(item)
            self.completed.append(item)
        self.save()

    # ---------- 유틸 ----------
    def fix_untagged(self, default_tag="(untagged)"):
        changed = False
        for it in self.active + self.completed:
            if not it.tags:
                it.tags.append(default_tag)
                changed = True
        if changed:
            self.save()
        return changed

# --------------------------- 간단 CLI -----------------------------
if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Learning Scheduler")
    sub = p.add_subparsers(dest="cmd")

    add_p = sub.add_parser("add")
    add_p.add_argument("content")
    add_p.add_argument("--summary", default="")
    add_p.add_argument("--tags",   default="")     # 쉼표 구분

    rev_p = sub.add_parser("review")

    list_p = sub.add_parser("list")
    list_p.add_argument("--tag")

    fix_p = sub.add_parser("fix-untagged")

    args = p.parse_args()
    db = LearningDB()

    if args.cmd == "add":
        tags = [t.strip() for t in args.tags.split(",") if t.strip()]
        db.add_item(args.content, summary=args.summary, tags=tags)
        print("✅ Added")

    elif args.cmd == "list":
        tags = [args.tag] if args.tag else None
        for it in db.get_due_items(tag_filter=tags):
            print(f"{it.id[:8]}|{it.tags}|{it.content[:60]}…")

    elif args.cmd == "review":
        for it in db.get_due_items():
            print("\n" + "-"*60)
            print(it.content)
            print("Tags:", ", ".join(it.tags) or "(none)")
            mark = input("O/Δ/X : ").upper()
            new_tag = input("추가 태그(쉼표, 엔터=없음): ").strip()
            new_tag_list = [t.strip() for t in new_tag.split(",") if t.strip()]
            db.review_item(it, mark, add_tags=new_tag_list)

    elif args.cmd == "fix-untagged":
        ok = db.fix_untagged()
        print("✅ filled" if ok else "모든 항목에 이미 태그가 있습니다.")
