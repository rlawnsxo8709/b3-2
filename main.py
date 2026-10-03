#!/usr/bin/env python3
"""python main.py commit | pr — 미션 예시와 동일한 실행 방법을 제공하는 진입점."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from aicommit.cli import main  # noqa: E402  (경로 설정 후 import)

if __name__ == "__main__":
    sys.exit(main())
