"""AI API 호출 — 표준 라이브러리만으로 REST 요청을 보낸다.

요청: POST {base_url}/chat/completions  (OpenAI Chat Completions 호환)
응답: choices[0].message.content
오류는 원인별 예외로 바꿔서 올려 보낸다. 호출 횟수는 calls 에 쌓인다.
"""

import json
import urllib.error
import urllib.request

from .config import (
    DEFAULT_BASE_URL,
    DEFAULT_TIMEOUT,
    PROVIDER_DEFAULT_TEMPERATURE,
    supports_custom_temperature,
)
from .errors import APIError, AuthError, NetworkError, RateLimitError, ResponseFormatError


def build_payload(messages, *, model, temperature, max_tokens):
    """요청 본문을 만든다.

    GPT-5·o 시리즈는 temperature 변경을 거부하므로, 기본값이 아닐 때는 아예 싣지 않는다.
    (파라미터를 빼면 공급자 기본값으로 동작한다)
    """
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if supports_custom_temperature(model) or temperature == PROVIDER_DEFAULT_TEMPERATURE:
        payload["temperature"] = temperature
    return payload


class AIClient:
    def __init__(self, api_key, base_url=DEFAULT_BASE_URL, timeout=DEFAULT_TIMEOUT):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.calls = 0

    def complete(self, messages, *, model, temperature, max_tokens):
        """메시지 배열을 보내고 생성된 텍스트를 돌려준다."""
        payload = build_payload(messages, model=model, temperature=temperature, max_tokens=max_tokens)
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
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

        return self._extract_content(raw)

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
    def _extract_content(raw):
        try:
            body = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ResponseFormatError("API 응답이 JSON 형식이 아닙니다.") from exc
        try:
            return body["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise ResponseFormatError("API 응답에서 생성 결과를 찾지 못했습니다.") from exc
