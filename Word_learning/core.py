# Word_learning/core.py

import json
from pathlib import Path
from datetime import datetime

# 기본 경로 (이후 Colab에서 덮어쓰게 됩니다)
BASE: Path = Path('.')
DATA_DIR: Path = None
WORDS_FILE: Path = None
AUDIO_DIR: Path = None

def setup_dirs():
    """데이터 및 오디오 캐시를 위한 디렉토리 구조를 설정합니다."""
    global DATA_DIR, WORDS_FILE, AUDIO_DIR
    DATA_DIR = BASE / 'data'
    AUDIO_DIR = DATA_DIR / 'audio_cache' / 'words_audio'
    WORDS_FILE = DATA_DIR / 'words.json'

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    if not WORDS_FILE.exists():
        WORDS_FILE.write_text('{}', encoding='utf-8')

def now_iso():
    """현재 시간을 UTC ISO 형식으로 반환합니다."""
    return datetime.utcnow().isoformat()

def load_db() -> dict:
    """단어 데이터베이스(words.json)를 불러옵니다."""
    return json.loads(WORDS_FILE.read_text(encoding='utf-8'))

def save_db(db: dict):
    """단어 데이터베이스(words.json)를 저장합니다."""
    WORDS_FILE.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding='utf-8')
