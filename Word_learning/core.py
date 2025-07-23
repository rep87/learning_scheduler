# Word_learning/core.py
"""
core.py
~~~~~~~
파일·폴더 경로 관리와 DB(load/save), 스키마 마이그레이션을 담당합니다.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

# ------------------------------------------------------------------
# 전역 경로
# ------------------------------------------------------------------
BASE: Path = Path(".")              # Colab 등에서 set_base_path()로 덮어쓰게 됨.
DATA_DIR: Path | None = None
WORDS_FILE: Path | None = None
AUDIO_DIR: Path | None = None

# ------------------------------------------------------------------
# 디렉토리·파일 초기화
# ------------------------------------------------------------------
def setup_dirs() -> None:
    """
    BASE/data 아래에 words.json, audio_cache/words_audio/ 를 준비합니다.
    BASE 값이 바뀔 때마다 반드시 호출해야 합니다.
    """
    global DATA_DIR, WORDS_FILE, AUDIO_DIR

    DATA_DIR = BASE / "data"
    AUDIO_DIR = DATA_DIR / "audio_cache" / "words_audio"
    WORDS_FILE = DATA_DIR / "words.json"

    # mkdir(parents=True) 는 존재해도 예외를 일으키지 않습니다.
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    # 빈 DB 파일 생성
    if not WORDS_FILE.exists():
        WORDS_FILE.write_text("{}", encoding="utf-8")

# ------------------------------------------------------------------
# 시간 헬퍼
# ------------------------------------------------------------------
def now_iso() -> str:
    """UTC ISO-8601 타임스탬프."""
    return datetime.utcnow().isoformat(timespec="seconds")

# ------------------------------------------------------------------
# DB 로드/저장 + 스키마 보정
# ------------------------------------------------------------------
_REQUIRED_MODES = ("choice", "recall", "spelling")

def _ensure_schema(rec: Dict[str, Any]) -> bool:
    """
    단어 레코드를 최신 스키마에 맞춰 보정합니다.
    수정이 일어나면 True, 아니면 False 반환.
    """
    changed = False

    # stats 딕트 보장
    stats = rec.setdefault("stats", {})
    if stats is None:               # 예전 버전이 null 로 저장된 경우
        stats = rec["stats"] = {}
        changed = True

    # 각 모드(choice/recall/spelling)의 c·w 카운터 보장
    for mode in _REQUIRED_MODES:
        mdict = stats.setdefault(mode, {})
        # setdefault가 새로 넣었으면 변경 표시
        if mdict is stats[mode] and (mdict.get("c") is None or mdict.get("w") is None):
            mdict.setdefault("c", 0)
            mdict.setdefault("w", 0)
            changed = True

    # added_at 누락 보정
    if "added_at" not in rec:
        rec["added_at"] = now_iso()
        changed = True

    return changed

def load_db() -> Dict[str, Any]:
    """
    words.json → dict.  
    • 파일이나 폴더가 아직 없다면 setup_dirs() 자동 호출  
    • 스키마 보정 수행 후 변경 시 즉시 저장
    """
    if WORDS_FILE is None or not WORDS_FILE.exists():
        setup_dirs()

    db: Dict[str, Any] = json.loads(WORDS_FILE.read_text(encoding="utf-8"))

    # 모든 레코드에 대해 스키마 보정
    changed = any(_ensure_schema(rec) for rec in db.values())
    if changed:
        save_db(db)   # 자동 업그레이드

    return db

def save_db(db: Dict[str, Any]) -> None:
    """dict → words.json"""
    if WORDS_FILE is None:
        setup_dirs()
    WORDS_FILE.write_text(
        json.dumps(db, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
