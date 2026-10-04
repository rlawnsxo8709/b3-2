"""AI API 호출 — 표준 라이브러리만으로 REST 요청을 보낸다.

두 가지 요청 형식을 지원한다.
  openai    : POST {base_url}/chat/completions → choices[0].message.content
  anthropic : POST {base_url}/messages         → content 블록 중 type=text 만 이어 붙인다
오류는 원인별 예외로 바꿔서 올려 보낸다. 호출 횟수는 calls 에 쌓인다.
"""

import json
import urllib.error
import urllib.request

from .config import (
    ANTHROPIC_EFFORT,
    ANTHROPIC_VERSION,
    DEFAULT_API_FORMAT,
    DEFAULT_BASE_URL,
    DEFAULT_TIMEOUT,
    is_current_claude,
    sends_temperature,
)
from .errors import APIError, AuthError, NetworkError, RateLimitError, ResponseFormatError

# 안전 분류기가 요청을 거절하면 서버가 Anthropic 권장 모델로 한 번 더 돌린다 (Anthropic 공식 API 전용 베타)
SERVER_FALLBACK_MODELS = ("claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5")
SERVER_FALLBACK_BETA = "server-side-fallback-2026-07-01"


def build_payload(messages, *, model, temperature, max_tokens):
    """OpenAI 형식 요청 본문.

    GPT-5·o 시리즈는 temperature 변경을 거부하므로, 기본값이 아닐 때는 아예 싣지 않는다.
    (파라미터를 빼면 공급자 기본값으로 동작한다)
    """
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if sends_temperature(model, temperature):
        payload["temperature"] = temperature
    return payload


def build_anthropic_payload(messages, *, model, temperature, max_tokens):
    """Anthropic Messages API 형식 요청 본문.

    system 은 messages 배열이 아니라 최상위 필드로 보낸다.
    Claude 4.7 이후 세대는 temperature 를 받지 않으므로 빼고, effort 로 사고 깊이를 낮춘다.
    """
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [m for m in messages if m["role"] != "system"],
    }
    if system:
        payload["system"] = system
    if sends_temperature(model, temperature):
        payload["temperature"] = temperature
    if is_current_claude(model):
        payload["output_config"] = {"effort": ANTHROPIC_EFFORT}
    if model in SERVER_FALLBACK_MODELS:
        payload["fallbacks"] = "default"
    return payload


class AIClient:
    def __init__(self, api_key, base_url=DEFAULT_BASE_URL, timeout=DEFAULT_TIMEOUT, api_format=DEFAULT_API_FORMAT):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.api_format = api_format
        self.calls = 0
        self.truncated = False  # 직전 응답이 max_tokens 에 걸려 중간에 잘렸는가

    def _request(self, messages, *, model, temperature, max_tokens):
        """형식에 맞는 (경로, 헤더, 본문)을 만든다."""
        params = {"model": model, "temperature": temperature, "max_tokens": max_tokens}
        if self.api_format == "anthropic":
            headers = {"x-api-key": self.api_key, "anthropic-version": ANTHROPIC_VERSION}
            if model in SERVER_FALLBACK_MODELS:
                headers["anthropic-beta"] = SERVER_FALLBACK_BETA
            return "/messages", headers, build_anthropic_payload(messages, **params)
        headers = {"Authorization": f"Bearer {self.api_key}"}
        return "/chat/completions", headers, build_payload(messages, **params)

    def complete(self, messages, *, model, temperature, max_tokens):
        """메시지 배열을 보내고 생성된 텍스트를 돌려준다."""
        path, headers, payload = self._request(messages, model=model, temperature=temperature, max_tokens=max_tokens)
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf8"),
            headers={**headers, "Content-Type": "application/json"},
            method="POST",
        )

        self.calls += 1  # 실패한 호출도 비용·한도에 포함되므로 함께 센다
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf8")
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc) from exc
        except TimeoutError as exc:
            raise NetworkError(f"API 응답이 {self.timeout}초 안에 오지 않았습니다. 네트워크 상태를 확인해 주세요.") from exc
        except urllib.error.URLError as exc:
            raise NetworkError(f"API 서버에 연결하지 못했습니다: {exc.reason}") from exc

        extract = self._extract_anthropic_content if self.api_format == "anthropic" else self._extract_content
        text, self.truncated = extract(raw)
        return text

    def _http_error(self, exc):
        detail = ""
        try:
            body = json.loads(exc.read().decode("utf8"))
            detail = body.get("error", {}).get("message", "")
        except Exception:  # 본문이 JSON 이 아닐 수도 있다
            pass
        suffix = f" ({detail})" if detail else ""

        if exc.code in (401, 403):
            return AuthError(f"API 인증에 실패했습니다. API Key 를 확인해 주세요.{suffix}")
        if exc.code == 429:
            return RateLimitError(f"API 요청 한도를 초과했습니다. 잠시 후 다시 시도해 주세요.{suffix}")
        if exc.code == 404:
            return APIError(f"엔드포인트 또는 모델을 찾을 수 없습니다. (HTTP 404){suffix}")
        return APIError(f"API 호출이 실패했습니다. (HTTP {exc.code}){suffix}")

    @staticmethod
    def _load_json(raw):
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ResponseFormatError("API 응답이 JSON 형식이 아닙니다.") from exc

    @classmethod
    def _extract_content(cls, raw):
        """(텍스트, 잘림 여부). finish_reason 이 length 면 max_tokens 에 걸려 잘린 것이다."""
        body = cls._load_json(raw)
        try:
            choice = body["choices"][0]
            return choice["message"]["content"].strip(), choice.get("finish_reason") == "length"
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise ResponseFormatError("API 응답에서 생성 결과를 찾지 못했습니다.") from exc

    @classmethod
    def _extract_anthropic_content(cls, raw):
        """(텍스트, 잘림 여부). content 블록 중 text 만 모은다 — thinking 블록은 보여줄 결과가 아니다."""
        body = cls._load_json(raw)
        if not isinstance(body, dict) or not isinstance(body.get("content"), list):
            raise ResponseFormatError("API 응답에서 생성 결과를 찾지 못했습니다.")

        stop_reason = body.get("stop_reason")
        if stop_reason == "refusal":  # 거절은 HTTP 200 으로 온다 — content 를 읽기 전에 확인한다
            category = (body.get("stop_details") or {}).get("category")
            suffix = f" (분류: {category})" if category else ""
            raise APIError(f"모델이 요청을 거절했습니다{suffix}. diff 내용이나 모델을 바꿔 다시 시도해 주세요.")

        text = "".join(
            block.get("text", "") for block in body["content"]
            if isinstance(block, dict) and block.get("type") == "text"
        ).strip()
        if not text and stop_reason == "max_tokens":
            raise ResponseFormatError("응답이 max_tokens 에 걸려 결과가 비었습니다. --max-tokens 를 늘려 주세요.")
        if not text:
            raise ResponseFormatError("API 응답에서 생성 결과를 찾지 못했습니다.")
        return text, stop_reason == "max_tokens"
