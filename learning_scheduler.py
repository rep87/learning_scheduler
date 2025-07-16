# learning_scheduler.py# learning_scheduler.py — tag‑enabled version\n"""\n Ultra Rapid Knowledge Cycling & Expansion (URKCE) — with tag filtering\n –––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––\n Core additions vs. previous version\n   • LearningItem.tags: list[str]\n   • add_item(..., tags=[])\n   • get_due_items(..., tag_filter=None)\n   • from_dict() backward‑compat with older JSON (no tags)\n"""\nfrom __future__ import annotations\n\nimport json, uuid\nfrom dataclasses import dataclass, asdict, field\nfrom datetime import date, timedelta\nfrom pathlib import Path\nfrom typing import List, Optional\n\nACTIVE_PATH = Path("learning_items.json")\nDONE_PATH   = Path("completed_items.json")\n\nINTERVALS = {0: 1, 1: 3, 2: 7, 3: 30}  # days until next review after O\n\n# ──────────────────────────────────────────────────────────────────────────────\n# LearningItem\n# ──────────────────────────────────────────────────────────────────────────────\n@dataclass\nclass LearningItem:\n    content: str\n    summary: str = ""\n    id: str = field(default_factory=lambda: str(uuid.uuid4()))\n    initial_date: str = field(default_factory=lambda: date.today().isoformat())\n    last_review_date: str = field(default_factory=lambda: date.today().isoformat())\n    next_review_date: str = field(default_factory=lambda: (date.today()+timedelta(days=1)).isoformat())\n    memory_count: int = 0           # 0‑3\n    status: str = "X"               # "O", "Δ", "X"\n    history: List[dict] = field(default_factory=list)\n    tags: List[str] = field(default_factory=list)\n\n    # ────────────────────────────────────────────────────────────────────────\n    def review(self, status: str, summary_update: Optional[str] = None):\n        status = status.upper()\n        assert status in {"O", "Δ", "X"}, "status must be O/Δ/X"\n        today = date.today().isoformat()\n        self.status = status\n        self.last_review_date = today\n        self.history.append({"date": today, "status": status})\n        if summary_update is not None:\n            self.summary = summary_update\n        if status == "O":\n            self.memory_count = min(self.memory_count + 1, 3)\n        elif status == "X":\n            self.memory_count = 0\n        self._schedule_next()\n\n    # ────────────────────────────────────────────────────────────────────────\n    def _schedule_next(self):\n        self.next_review_date = (date.today() + timedelta(days=INTERVALS[self.memory_count])).isoformat()\n\n    def is_due(self, on: date) -> bool:\n        return date.fromisoformat(self.next_review_date) <= on\n\n    def to_dict(self):\n        return asdict(self)\n\n    @staticmethod\n    def from_dict(d: dict) -> "LearningItem":\n        if "tags" not in d:   # backward‑compat\n            d["tags"] = []\n        return LearningItem(**d)\n\n# ──────────────────────────────────────────────────────────────────────────────\n# LearningDB\n# ──────────────────────────────────────────────────────────────────────────────\nclass LearningDB:\n    def __init__(self, active_path: Path = ACTIVE_PATH, done_path: Path = DONE_PATH):\n        self.active_path = active_path\n        self.done_path   = done_path\n        self.active:   List[LearningItem] = []\n        self.completed: List[LearningItem] = []\n        self.load()\n\n    # —— file IO ——\n    def load(self):\n        self.active    = self._load_file(self.active_path)\n        self.completed = self._load_file(self.done_path)\n\n    def save(self):\n        self._save_file(self.active_path, self.active)\n        self._save_file(self.done_path, self.completed)\n\n    def _load_file(self, path: Path) -> List[LearningItem]:\n        if not path.exists():\n            return []\n        with path.open("r", encoding="utf‑8") as f:\n            raw = json.load(f)\n        return [LearningItem.from_dict(x) for x in raw]\n\n    def _save_file(self, path: Path, items: List[LearningItem]):\n        with path.open("w", encoding="utf‑8") as f:\n            json.dump([it.to_dict() for it in items], f, ensure_ascii=False, indent=2)\n\n    # —— creation ——\n    def add_item(self, content: str, summary: str = "", tags: list[str] | None = None) -> LearningItem:\n        it = LearningItem(content=content, summary=summary, tags=tags or [])\n        self.active.append(it)\n        self.save()\n        return it\n\n    # —— querying ——\n    def get_due_items(self, on: date = date.today(), tag_filter: list[str] | None = None) -> List[LearningItem]:\n        # 1) date filter\n        pool = [it for it in self.active if it.is_due(on)]\n        # 2) tag filter (if any)\n        if tag_filter:\n            wanted = {t.lower() for t in tag_filter}\n            pool = [it for it in pool if wanted & {t.lower() for t in it.tags}]\n        # 3) priority sort\n        pool.sort(key=lambda x: (date.fromisoformat(x.next_review_date), x.memory_count, x.status == "X"))\n        return pool\n\n    # —— review ——\n    def review_item(self, item: LearningItem, status: str, summary_update: Optional[str] = None):\n        item.review(status, summary_update)\n        if item.memory_count >= 3 and status == "O":\n            self.active.remove(item)\n            self.completed.append(item)\n        self.save()

"""Ultra Rapid Knowledge Cycling & Expansion (URKCE)
-------------------------------------------------------------------------------
A lightweight Python library + CLI that implements the learning workflow we 
designed:
  • Spaced‑repetition with custom O/Δ/X marking
  • Automatic priority when sessions are skipped
  • Persistent history for every item
  • Separation of active vs. completed items

Main abstractions
=================
LearningItem
    Represents a single piece of knowledge. Handles review updates and next‑date
    scheduling logic.

LearningDB
    Manages collections of LearningItem objects, loading/saving JSON files and
    selecting which items are due.

Quick start
===========
1.  python learning_scheduler.py add "Your content here" --summary "short note"
2.  python learning_scheduler.py review   # repeatedly prompts due items
3.  python learning_scheduler.py list --all‑due

JSON files created in the working directory:
  • learning_items.json      – active (due/not‑yet‑done) items
  • completed_items.json     – memory_count == 3 (mastered)

You can later visualize, export to Excel, or connect to a chatbot front‑end.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, asdict, field
from datetime import date, timedelta, datetime
from pathlib import Path
from typing import List, Optional

ACTIVE_PATH = Path("learning_items.json")
DONE_PATH = Path("completed_items.json")

# ----------------------------------------------------------------------------
# Core model
# ----------------------------------------------------------------------------

INTERVALS = {0: 1, 1: 3, 2: 7, 3: 30}  # days for next review after O‑mark

@dataclass
class LearningItem:
    content: str
    summary: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    initial_date: str = field(default_factory=lambda: date.today().isoformat())
    last_review_date: str = field(default_factory=lambda: date.today().isoformat())
    next_review_date: str = field(default_factory=lambda: (date.today() + timedelta(days=1)).isoformat())
    memory_count: int = 0  # 0‑3
    status: str = "X"  # "O", "Δ", "X"
    history: List[dict] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    # ---------------------------------------------------------------------
    # Logic helpers
    # ---------------------------------------------------------------------

    def review(self, status: str, summary_update: Optional[str] = None) -> None:
        """Update item after a review mark (O/Δ/X)."""
        status = status.upper()
        if status not in {"O", "Δ", "X"}:
            raise ValueError("status must be 'O', 'Δ', or 'X'")

        today = date.today()
        self.status = status
        self.last_review_date = today.isoformat()
        self.history.append({"date": today.isoformat(), "status": status})

        if summary_update is not None:
            self.summary = summary_update

        if status == "O":
            self.memory_count = min(self.memory_count + 1, 3)
        elif status == "X":
            self.memory_count = 0
        # Δ keeps memory_count unchanged

        self._schedule_next()

    # ------------------------------------------------------------------
    def is_due(self, on: date) -> bool:
        return date.fromisoformat(self.next_review_date) <= on

    # ------------------------------------------------------------------
    def _schedule_next(self):
        interval_days = INTERVALS[self.memory_count]
        self.next_review_date = (date.today() + timedelta(days=interval_days)).isoformat()

    # ------------------------------------------------------------------
    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "LearningItem":
        return LearningItem(**d)

# ----------------------------------------------------------------------------
# Database wrapper
# ----------------------------------------------------------------------------
class LearningDB:
    def __init__(self, active_path: Path = ACTIVE_PATH, done_path: Path = DONE_PATH):
        self.active_path = active_path
        self.done_path = done_path
        self.active: List[LearningItem] = []
        self.completed: List[LearningItem] = []
        self.load()

    # ------------------------------------------------------------------
    def load(self):
        self.active = self._load_file(self.active_path)
        self.completed = self._load_file(self.done_path)

    # ------------------------------------------------------------------
    def save(self):
        self._save_file(self.active_path, self.active)
        self._save_file(self.done_path, self.completed)

    # ------------------------------------------------------------------
    def _load_file(self, path: Path) -> List[LearningItem]:
        if not path.exists():
            return []
        with path.open("r", encoding="utf‑8") as f:
            raw = json.load(f)
        return [LearningItem.from_dict(x) for x in raw]

    # ------------------------------------------------------------------
    def _save_file(self, path: Path, items: List[LearningItem]):
        with path.open("w", encoding="utf‑8") as f:
            json.dump([it.to_dict() for it in items], f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    def add_item(
            self,
            content: str,
            summary: str = "",
            tags: list[str] | None = None,   # ⭐ 추가
        ) -> LearningItem:
        it = LearningItem(
            content=content,
            summary=summary,
            tags=tags or []                  # None → 빈 리스트
        )
        self.active.append(it)
        self.save()
        return it


    # ------------------------------------------------------------------
    def get_due_items(
            self,
            on: date = date.today(),
            tag_filter: list[str] | None = None,
        ) -> List[LearningItem]:
        """
        반환:
            - today(기본) 또는 원하는 날짜까지 복습 대상
            - tag_filter가 주어지면, 해당 태그와 교집합이 있는 항목만
        """
        # 1) 날짜 기준 필터
        pool = [it for it in self.active if it.is_due(on)]
    
        # 2) 태그 필터(옵션)
        if tag_filter:
            wanted = {t.lower() for t in tag_filter}
            pool = [
                it for it in pool
                if wanted & {t.lower() for t in it.tags}  # 교집합 존재
            ]
    
        # 3) 우선순위 정렬 그대로
        pool.sort(key=lambda x: (
            date.fromisoformat(x.next_review_date),
            x.memory_count,
            x.status == "X",
        ))
        return pool


    # ------------------------------------------------------------------
    def review_item(self, item: LearningItem, status: str, summary_update: Optional[str] = None):
        item.review(status, summary_update)
        if item.memory_count >= 3 and status == "O":
            self.active.remove(item)
            self.completed.append(item)
        self.save()

    def from_dict(d: dict) -> "LearningItem":
    if "tags" not in d:          # 예전 JSON엔 없을 수 있음
        d["tags"] = []
    return LearningItem(**d)

# ----------------------------------------------------------------------------
# Simple CLI entry‐point
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse, textwrap

    parser = argparse.ArgumentParser(description="URKCE learning scheduler")
    sub = parser.add_subparsers(dest="cmd")

    # add command
    add_p = sub.add_parser("add", help="Add new learning item")
    add_p.add_argument("content")
    add_p.add_argument("--summary", default="", help="optional short summary")

    # review command
    rev_p = sub.add_parser("review", help="Interactive review session for due items")

    # list command
    list_p = sub.add_parser("list", help="List items (all or due)")
    list_p.add_argument("--all", action="store_true", help="show all active items")
    list_p.add_argument("--completed", action="store_true", help="show mastered items")

    args = parser.parse_args()

    db = LearningDB()

    if args.cmd == "add":
        item = db.add_item(args.content, args.summary)
        print(f"Added item: {item.id}")

    elif args.cmd == "review":
        due = db.get_due_items()
        if not due:
            print("🎉 Nothing due today! Great job.")
            exit(0)
        for item in due:
            print("\n" + "-" * 60)
            print(textwrap.fill(item.content, 80))
            if item.summary:
                print(f"\n[Summary] {item.summary}")
            status = ""
            while status.upper() not in {"O", "Δ", "X"}:
                status = input("Mark (O/Δ/X): ")
            new_summary = input("(Optional) Update summary > ").strip()
            db.review_item(item, status, summary_update=new_summary or None)
        print("\n✅ Session complete. See you next time!")

    elif args.cmd == "list":
        if args.completed:
            items = db.completed
        else:
            items = db.active
            if not args.all:
                items = db.get_due_items()
        for it in items:
            print(f"{it.id[:8]} | next={it.next_review_date} | mc={it.memory_count} | status={it.status} | {it.content[:60]}…")
        print(f"Total: {len(items)} items")

    else:
        parser.print_help()
