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


if __name__ == "__main__":
    unittest.main()


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
