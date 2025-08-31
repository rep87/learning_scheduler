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
BASE: Path = Path(".")              # Colab 등에서 set_base_path()로 덮어씀
DATA_DIR: Path | None = None
WORDS_FILE: Path | None = None

# 오디오 캐시: 단어/문장 분리
AUDIO_WORD_DIR: Path | None = None   # data/audio_cache/words_audio
AUDIO_SENT_DIR: Path | None = None   # data/audio_cache/sentences_audio

# 과거 코드 호환: 예전에는 AUDIO_DIR만 사용 → 단어 경로로 별칭 유지
AUDIO_DIR: Path | None = None

# 퀴즈 세션 로그 파일 경로
QUIZZES_FILE: Path | None = None     # data/quizzes.jsonl


# ------------------------------------------------------------------
# BASE 설정
# ------------------------------------------------------------------
def set_base_path(base: str | Path) -> None:
    """
    BASE 경로를 지정하고 폴더/파일을 초기화합니다.
    예: set_base_path('/content/drive/MyDrive/Projects/learning_scheduler')
    """
    global BASE
    BASE = Path(base)
    setup_dirs()


# ------------------------------------------------------------------
# 디렉토리·파일 초기화
# ------------------------------------------------------------------
def setup_dirs() -> None:
    """
    BASE/data 아래에 words.json,
    audio_cache/words_audio/, audio_cache/sentences_audio/ 를 준비합니다.
    BASE 값이 바뀔 때마다 반드시 호출해야 합니다.
    """
    global DATA_DIR, WORDS_FILE, AUDIO_WORD_DIR, AUDIO_SENT_DIR, AUDIO_DIR, QUIZZES_FILE

    DATA_DIR = BASE / "data"
    WORDS_FILE = DATA_DIR / "words.json"
    QUIZZES_FILE = DATA_DIR / "quizzes.jsonl"

    # 오디오 캐시 경로 (단어/문장 분리)
    AUDIO_WORD_DIR = DATA_DIR / "audio_cache" / "words_audio"
    AUDIO_SENT_DIR = DATA_DIR / "audio_cache" / "sentences_audio"

    # 레거시 호환: AUDIO_DIR 는 단어 오디오 경로로 유지
    AUDIO_DIR = AUDIO_WORD_DIR

    # 필수 디렉토리 생성
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_WORD_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_SENT_DIR.mkdir(parents=True, exist_ok=True)

    # 빈 DB 파일/세션 로그 생성
    if not WORDS_FILE.exists():
        WORDS_FILE.write_text("{}", encoding="utf-8")
    if not QUIZZES_FILE.exists():
        QUIZZES_FILE.touch()


# ------------------------------------------------------------------
# 시간 헬퍼
# ------------------------------------------------------------------
def now_iso() -> str:
    """UTC ISO-8601 타임스탬프."""
    return datetime.utcnow().isoformat(timespec="seconds")


# ------------------------------------------------------------------
# DB 로드/저장 + 스키마 보정
# ------------------------------------------------------------------
# sentence 모드 추가 (단어 외에 문장 학습용)
_REQUIRED_MODES = ("choice", "recall", "spelling", "sentence")


def _ensure_schema(rec: Dict[str, Any]) -> bool:
    """
    레코드를 최신 스키마에 맞춰 보정합니다.
    변경이 발생하면 True, 아니면 False 반환.
    """
    changed = False

    # 기본 필드 보장: tags, examples, definition_en
    if "tags" not in rec or rec["tags"] is None:
        rec["tags"] = []
        changed = True
    elif not isinstance(rec["tags"], list):
        rec["tags"] = [rec["tags"]]
        changed = True

    if "examples" not in rec or rec["examples"] is None:
        rec["examples"] = []
        changed = True

    if "definition_en" not in rec:
        rec["definition_en"] = ""
        changed = True

    # stats 딕트 보장
    stats = rec.setdefault("stats", {})
    if stats is None:  # 예전 버전이 null로 저장된 경우
        stats = rec["stats"] = {}
        changed = True

    # 각 모드(choice/recall/spelling/sentence)의 c·w 카운터 보장
    for mode in _REQUIRED_MODES:
        mdict = stats.setdefault(mode, {})
        if "c" not in mdict:
            mdict["c"] = 0
            changed = True
        if "w" not in mdict:
            mdict["w"] = 0
            changed = True
        # 필요 시 최근 날짜(last) 같은 필드도 여기서 추가 가능
        # if "last" not in mdict:
        #     mdict["last"] = None
        #     changed = True

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
        save_db(db)  # 자동 업그레이드

    return db


def save_db(db: Dict[str, Any]) -> None:
    """dict → words.json"""
    if WORDS_FILE is None:
        setup_dirs()
    WORDS_FILE.write_text(
        json.dumps(db, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
