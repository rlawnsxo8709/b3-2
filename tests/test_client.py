"""AI API 클라이언트 — 요청 구성, 응답 처리, 오류 분류."""

import unittest

from aicommit.client import AIClient
from aicommit.errors import APIError, AuthError, NetworkError, RateLimitError, ResponseFormatError
from tests.stub_server import StubAPI

MESSAGES = [{"role": "user", "content": "안녕"}]


class RequestTest(unittest.TestCase):
    def test_sends_model_and_parameters(self):
        with StubAPI() as stub:
            AIClient("test-key", stub.url).complete(MESSAGES, model="gpt-4o-mini", temperature=0.3, max_tokens=500)
            sent = stub.requests[0]["json"]
            self.assertEqual(sent["model"], "gpt-4o-mini")
            self.assertEqual(sent["temperature"], 0.3)
            self.assertEqual(sent["max_tokens"], 500)
            self.assertEqual(sent["messages"], MESSAGES)

    def test_sends_bearer_authorization_header(self):
        with StubAPI() as stub:
            AIClient("test-key", stub.url).complete(MESSAGES, model="m", temperature=0.2, max_tokens=10)
            self.assertEqual(stub.requests[0]["headers"]["Authorization"], "Bearer test-key")

    def test_calls_chat_completions_path(self):
        with StubAPI() as stub:
            AIClient("test-key", stub.url).complete(MESSAGES, model="m", temperature=0.2, max_tokens=10)
            self.assertEqual(stub.requests[0]["path"], "/v1/chat/completions")

    def test_returns_message_content(self):
        with StubAPI(responses=["feat: 결과 텍스트"]) as stub:
            text = AIClient("k", stub.url).complete(MESSAGES, model="m", temperature=0.2, max_tokens=10)
            self.assertEqual(text, "feat: 결과 텍스트")

    def test_counts_calls(self):
        with StubAPI() as stub:
            client = AIClient("k", stub.url)
            client.complete(MESSAGES, model="m", temperature=0.2, max_tokens=10)
            client.complete(MESSAGES, model="m", temperature=0.2, max_tokens=10)
            self.assertEqual(client.calls, 2)


class ErrorTest(unittest.TestCase):
    def call(self, **stub_kwargs):
        with StubAPI(**stub_kwargs) as stub:
            AIClient("k", stub.url, timeout=1).complete(MESSAGES, model="m", temperature=0.2, max_tokens=10)

    def test_401_raises_auth_error(self):
        with self.assertRaises(AuthError) as cm:
            self.call(status=401)
        self.assertIn("인증", str(cm.exception))

    def test_429_raises_rate_limit_error(self):
        with self.assertRaises(RateLimitError):
            self.call(status=429)

    def test_500_raises_api_error_with_status(self):
        with self.assertRaises(APIError) as cm:
            self.call(status=500)
        self.assertIn("500", str(cm.exception))

    def test_invalid_json_raises_response_format_error(self):
        with self.assertRaises(ResponseFormatError):
            self.call(body="not json at all")

    def test_missing_choices_raises_response_format_error(self):
        with self.assertRaises(ResponseFormatError):
            self.call(body='{"unexpected": true}')

    def test_timeout_raises_network_error(self):
        with self.assertRaises(NetworkError):
            self.call(delay=2.0)

    def test_unreachable_host_raises_network_error(self):
        client = AIClient("k", "http://127.0.0.1:1/v1", timeout=1)
        with self.assertRaises(NetworkError):
            client.complete(MESSAGES, model="m", temperature=0.2, max_tokens=10)





class PayloadParameterTest(unittest.TestCase):
    """GPT-5 계열은 temperature 변경을 지원하지 않는다 — 지원하는 모델에만 실어 보낸다."""

    def payload_for(self, model, temperature):
        with StubAPI() as stub:
            AIClient("k", stub.url).complete(MESSAGES, model=model, temperature=temperature, max_tokens=50)
            return stub.requests[0]["json"]

    def test_includes_temperature_for_models_that_support_it(self):
        for model in ("gpt-4o-mini", "claude-sonnet-4", "gemini-3-flash"):
            self.assertEqual(self.payload_for(model, 0.2)["temperature"], 0.2, model)

    def test_omits_temperature_for_gpt5_family(self):
        for model in ("gpt-5.5", "gpt-5-mini", "gpt-5.4-mini", "o3-mini"):
            self.assertNotIn("temperature", self.payload_for(model, 0.2), model)

    def test_keeps_default_temperature_for_gpt5_family(self):
        # 기본값(1)은 공급자가 받아들이므로 굳이 빼지 않는다
        self.assertEqual(self.payload_for("gpt-5.5", 1.0)["temperature"], 1.0)

    def test_always_sends_model_messages_and_max_tokens(self):
        payload = self.payload_for("gpt-5.5", 0.2)
        self.assertEqual(payload["model"], "gpt-5.5")
        self.assertEqual(payload["messages"], MESSAGES)
        self.assertEqual(payload["max_tokens"], 50)


SYSTEM_AND_USER = [
    {"role": "system", "content": "너는 커밋 메시지를 쓴다."},
    {"role": "user", "content": "변경 사항"},
]


class AnthropicFormatTest(unittest.TestCase):
    """api_format="anthropic" — POST {base}/messages, x-api-key 헤더, content 블록 응답."""

    def call(self, model="claude-opus-5-5", temperature=0.2, max_tokens=16000, **stub_kw):
        stub_kw.setdefault("api_format", "anthropic")
        with StubAPI(**stub_kw) as stub:
            client = AIClient("test-key", stub.url, api_format="anthropic")
            text = client.complete(SYSTEM_AND_USER, model=model, temperature=temperature, max_tokens=max_tokens)
            return text, stub.requests[0]

    def test_calls_messages_path(self):
        _, request = self.call()
        self.assertEqual(request["path"], "/v1/messages")

    def test_sends_api_key_and_version_headers(self):
        _, request = self.call()
        headers = {k.lower(): v for k, v in request["headers"].items()}
        self.assertEqual(headers["x-api-key"], "test-key")
        self.assertEqual(headers["anthropic-version"], "2023-06-01")
        self.assertNotIn("authorization", headers)

    def test_moves_system_message_to_top_level(self):
        _, request = self.call()
        payload = request["json"]
        self.assertEqual(payload["system"], "너는 커밋 메시지를 쓴다.")
        self.assertEqual(payload["messages"], [{"role": "user", "content": "변경 사항"}])
        self.assertEqual(payload["max_tokens"], 16000)

    def test_returns_only_text_blocks(self):
        text, _ = self.call(responses=["feat: 응답"])
        self.assertEqual(text, "feat: 응답")

    def test_current_claude_models_get_no_temperature_and_low_effort(self):
        # Claude 4.7 이후 세대는 temperature 를 받지 않는다(기본값 1 도 거부) — 사고 깊이는 effort 로 조절한다
        for model in ("claude-opus-5-5", "claude-sonnet-5-5", "claude-opus-4-7"):
            for temperature in (0.2, 1.0):
                _, request = self.call(model=model, temperature=temperature)
                self.assertNotIn("temperature", request["json"], model)
                self.assertEqual(request["json"]["output_config"], {"effort": "low"}, model)

    def test_older_claude_models_keep_temperature(self):
        _, request = self.call(model="claude-haiku-4-5", temperature=0.3)
        self.assertEqual(request["json"]["temperature"], 0.3)
        self.assertNotIn("output_config", request["json"])

    def test_refusal_raises_api_error(self):
        body = '{"content": [], "stop_reason": "refusal", "stop_details": {"category": "cyber"}}'
        with self.assertRaises(APIError) as ctx:
            self.call(body=body)
        self.assertIn("거절", str(ctx.exception))

    def test_max_tokens_without_text_suggests_more_tokens(self):
        body = '{"content": [{"type": "thinking", "thinking": ""}], "stop_reason": "max_tokens"}'
        with self.assertRaises(ResponseFormatError) as ctx:
            self.call(body=body)
        self.assertIn("--max-tokens", str(ctx.exception))

    def test_missing_content_raises_response_format_error(self):
        with self.assertRaises(ResponseFormatError):
            self.call(body='{"choices": []}')

    def test_401_raises_auth_error(self):
        with self.assertRaises(AuthError):
            self.call(status=401)


if __name__ == "__main__":
    unittest.main()
