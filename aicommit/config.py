"""기본값과 환경변수 처리.

API Key 는 코드에 두지 않고 환경변수로만 받는다.
편의를 위해 실행 디렉토리의 .env 파일도 읽지만, 이미 설정된 환경변수를 덮어쓰지 않는다.
"""

import os
from pathlib import Path

from .errors import AICommitError, MissingAPIKey

# 요청 형식 — openai: POST {base}/chat/completions / anthropic: POST {base}/messages (Messages API)
API_FORMATS = ("openai", "anthropic")
DEFAULT_API_FORMAT = "anthropic"
API_FORMAT_ENV = "AI_API_FORMAT"

# 형식별 기본값. anthropic 기본 모델은 --temperature 가 실제로 적용되는 claude-sonnet-4 다
# (claude-opus-4-7/4-8 은 temperature 를 지원하지 않아 게이트웨이가 값을 무시한다).
# Anthropic 공식 API 를 쓰면 --model claude-opus-5-5 처럼 최신 모델을 지정한다.
# Claude 최신 모델은 사고(thinking) 토큰도 max_tokens 에 포함되므로 넉넉히 둔다
DEFAULT_MODELS = {"openai": "gpt-5.5", "anthropic": "claude-sonnet-4"}
# max_tokens 는 상한이다(실제 생성한 만큼만 과금). 실측한 출력 최대는 commit 268 · pr 1159 토큰이었다(README 참고)
DEFAULT_MAX_TOKENS = {"openai": 2000, "anthropic": 16000}
DEFAULT_TEMPERATURE = 0.2
# 형식별 temperature 허용 범위 — 밖이면 공급자가 400 으로 거부하므로 호출 전에 막는다
TEMPERATURE_RANGES = {"openai": (0.0, 2.0), "anthropic": (0.0, 1.0)}
DEFAULT_BASE_URL = "https://copa.codyssey.kr/v1"

# GPT-5·o 시리즈는 temperature 기본값(1)만 받는다. 다른 값을 보내면 공급자가 요청을 거부한다.
FIXED_TEMPERATURE_PREFIXES = ("gpt-5", "o1", "o3", "o4")
# Claude 4.7 이후 세대는 temperature 자체를 받지 않는다(기본값도 거부). 사고 깊이는 effort 로 조절한다.
CURRENT_CLAUDE_PREFIXES = ("claude-opus-5", "claude-opus-4-7", "claude-opus-4-8",
                           "claude-sonnet-5", "claude-fable", "claude-mythos")
PROVIDER_DEFAULT_TEMPERATURE = 1.0
# 커밋 메시지 요약은 단순한 작업이라 깊은 사고가 필요 없다 — 비용과 지연을 줄인다
ANTHROPIC_EFFORT = "low"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_TIMEOUT = 30
DEFAULT_MAX_FILES = 10
DEFAULT_MAX_LINES = 200

API_KEY_ENVS = {
    "openai": ("AI_API_KEY", "OPENAI_API_KEY"),
    "anthropic": ("AI_API_KEY", "ANTHROPIC_API_KEY"),
}
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


def resolve_api_format(cli_value=None, env=None):
    env = os.environ if env is None else env
    value = (cli_value or env.get(API_FORMAT_ENV) or DEFAULT_API_FORMAT).strip().lower()
    if value not in API_FORMATS:
        raise AICommitError(
            f"{API_FORMAT_ENV} 값 '{value}' 을(를) 알 수 없습니다. {' 또는 '.join(API_FORMATS)} 중 하나를 써 주세요."
        )
    return value


def check_temperature(api_format, temperature):
    """형식별 허용 범위를 벗어나면 API 를 부르기 전에 사용 오류로 알린다."""
    low, high = TEMPERATURE_RANGES[api_format]
    if not low <= temperature <= high:
        raise AICommitError(f"{api_format} 형식의 temperature 는 {low}~{high} 범위여야 합니다. (지정: {temperature})")


def resolve_api_key(api_format=DEFAULT_API_FORMAT, env=None):
    env = os.environ if env is None else env
    names = API_KEY_ENVS[api_format]
    for name in names:
        if env.get(name):
            return env[name]
    raise MissingAPIKey(
        f"{names[0]} 환경변수가 설정되지 않았습니다.\n"
        f'       예) export {names[0]}="YOUR_KEY"   또는 프로젝트 루트에 .env 파일 작성'
    )


def is_current_claude(model):
    """temperature 대신 effort 로 조절하는 Claude 4.7 이후 세대인가."""
    return model.lower().startswith(CURRENT_CLAUDE_PREFIXES)


def supports_custom_temperature(model):
    """이 모델이 temperature 변경을 받아들이는가."""
    return not (model.lower().startswith(FIXED_TEMPERATURE_PREFIXES) or is_current_claude(model))


def sends_temperature(model, temperature):
    """요청 본문에 temperature 를 실어도 되는가. 빼면 공급자 기본값으로 동작한다."""
    if supports_custom_temperature(model):
        return True
    return temperature == PROVIDER_DEFAULT_TEMPERATURE and not is_current_claude(model)


def resolve_base_url(cli_value=None, env=None):
    env = os.environ if env is None else env
    if cli_value:
        return cli_value.rstrip("/")
    for name in BASE_URL_ENVS:
        if env.get(name):
            return env[name].rstrip("/")
    return DEFAULT_BASE_URL
