"""기본값과 환경변수 처리.

API Key 는 코드에 두지 않고 환경변수로만 받는다.
편의를 위해 실행 디렉토리의 .env 파일도 읽지만, 이미 설정된 환경변수를 덮어쓰지 않는다.
"""

import os
from pathlib import Path

from .errors import MissingAPIKey

DEFAULT_MODEL = "gpt-5.5"
DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_TOKENS = 700
DEFAULT_BASE_URL = "https://copa.codyssey.kr/v1"

# GPT-5·o 시리즈는 temperature 기본값(1)만 받는다. 다른 값을 보내면 공급자가 요청을 거부한다.
FIXED_TEMPERATURE_PREFIXES = ("gpt-5", "o1", "o3", "o4")
PROVIDER_DEFAULT_TEMPERATURE = 1.0
DEFAULT_TIMEOUT = 30
DEFAULT_MAX_FILES = 10
DEFAULT_MAX_LINES = 200

API_KEY_ENVS = ("AI_API_KEY", "OPENAI_API_KEY")
BASE_URL_ENVS = ("AI_API_BASE_URL", "OPENAI_BASE_URL")


def parse_env_file(text):
    """KEY=VALUE 줄만 뽑아 dict 로 돌려준다. 주석(#)과 빈 줄은 건너뛴다."""
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("\"'")
    return values


def apply_env_file(directory="."):
    """<directory>/.env 가 있으면 비어 있는 환경변수만 채운다."""
    path = Path(directory) / ".env"
    if not path.is_file():
        return {}
    values = parse_env_file(path.read_text(encoding="utf8"))
    applied = {}
    for key, value in values.items():
        if not os.environ.get(key):
            os.environ[key] = value
            applied[key] = value
    return applied


def resolve_api_key(env=None):
    env = os.environ if env is None else env
    for name in API_KEY_ENVS:
        if env.get(name):
            return env[name]
    raise MissingAPIKey(
        f"{API_KEY_ENVS[0]} 환경변수가 설정되지 않았습니다.\n"
        f'       예) export {API_KEY_ENVS[0]}="YOUR_KEY"   또는 프로젝트 루트에 .env 파일 작성'
    )


def supports_custom_temperature(model):
    """이 모델이 temperature 변경을 받아들이는가."""
    return not model.lower().startswith(FIXED_TEMPERATURE_PREFIXES)


def resolve_base_url(cli_value=None, env=None):
    env = os.environ if env is None else env
    if cli_value:
        return cli_value.rstrip("/")
    for name in BASE_URL_ENVS:
        if env.get(name):
            return env[name].rstrip("/")
    return DEFAULT_BASE_URL
