"""CLI 전체 흐름 — 실제 git 저장소 + 실제 HTTP 스텁 서버로 main.py를 실행한다."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.stub_server import StubAPI

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MAIN = str(PROJECT_ROOT / "main.py")

PR_OK = """TITLE: feat: 커밋/PR 자동 생성 기능 추가
BODY:
## Why
- 커밋 메시지 작성 시간을 줄이기 위해
## What
- git diff 수집과 AI 호출 연결
## How to Test
- python main.py commit 실행
"""
COMMIT_OK = "feat: 변경 사항 요약 기능 추가\n\n- app.py 수정\n- 테스트 추가\n"


def git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


class CliTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        git(self.repo, "init", "-q", "-b", "feature/demo")
        git(self.repo, "config", "user.email", "test@example.com")
        git(self.repo, "config", "user.name", "test")
        (self.repo / "app.py").write_text("print('hello')\n", encoding="utf8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "init")

    def tearDown(self):
        self._tmp.cleanup()

    def change_file(self, text="print('changed')\n"):
        (self.repo / "app.py").write_text(text, encoding="utf8")

    def run_cli(self, *args, key="test-key", cwd=None, extra_env=None):
        env = {**os.environ, "PYTHONPATH": str(PROJECT_ROOT)}
        for name in ("AI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "AI_API_FORMAT", "AI_API_BASE_URL"):
            env.pop(name, None)
        if key is not None:
            env["AI_API_KEY"] = key
        env.update(extra_env or {})
        return subprocess.run(
            [sys.executable, MAIN, *args],
            cwd=str(cwd or self.repo), env=env, capture_output=True, text=True,
        )


class CommitCommandTest(CliTestBase):
    def test_prints_commit_message_between_separators(self):
        self.change_file()
        with StubAPI(responses=[COMMIT_OK]) as stub:
            result = self.run_cli("commit", "--base-url", stub.url)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Commit Message", result.stdout)
        self.assertIn("feat: 변경 사항 요약 기능 추가", result.stdout)
        self.assertIn("- app.py 수정", result.stdout)

    def test_reports_api_call_count(self):
        self.change_file()
        with StubAPI(responses=[COMMIT_OK]) as stub:
            result = self.run_cli("commit", "--base-url", stub.url)
        self.assertIn("1회", result.stdout)
        self.assertEqual(stub.call_count, 1)

    def test_sends_cli_parameters_to_api(self):
        self.change_file()
        with StubAPI(responses=[COMMIT_OK]) as stub:
            self.run_cli("commit", "--base-url", stub.url, "--model", "gpt-4.1-mini",
                         "--temperature", "0.9", "--max-tokens", "123")
            sent = stub.requests[0]["json"]
        self.assertEqual(sent["model"], "gpt-4.1-mini")
        self.assertEqual(sent["temperature"], 0.9)
        self.assertEqual(sent["max_tokens"], 123)

    def test_retries_once_when_format_is_invalid(self):
        self.change_file()
        bad = "제목 없이 " + "가" * 200
        with StubAPI(responses=[bad, COMMIT_OK]) as stub:
            result = self.run_cli("commit", "--base-url", stub.url)
        self.assertEqual(stub.call_count, 2)
        self.assertIn("feat: 변경 사항 요약 기능 추가", result.stdout)
        self.assertIn("2회", result.stdout)

    def test_no_retry_option_keeps_single_call(self):
        self.change_file()
        with StubAPI(responses=["제목 없이 " + "가" * 200]) as stub:
            self.run_cli("commit", "--base-url", stub.url, "--no-retry")
            self.assertEqual(stub.call_count, 1)

    def test_safe_mode_masks_secret_before_sending(self):
        self.change_file("API_KEY = 'sk-proj-abcd1234EFGH5678ijkl'\n")
        with StubAPI(responses=[COMMIT_OK]) as stub:
            self.run_cli("commit", "--base-url", stub.url)
            sent = str(stub.requests[0]["json"])
        self.assertNotIn("sk-proj-abcd1234EFGH5678ijkl", sent)
        self.assertIn("MASKED", sent)

    def test_no_safe_mode_sends_raw_diff(self):
        self.change_file("API_KEY = 'sk-proj-abcd1234EFGH5678ijkl'\n")
        with StubAPI(responses=[COMMIT_OK]) as stub:
            self.run_cli("commit", "--base-url", stub.url, "--no-safe-mode")
            self.assertIn("sk-proj-abcd1234EFGH5678ijkl", str(stub.requests[0]["json"]))

    def test_dry_run_does_not_call_api(self):
        self.change_file()
        with StubAPI() as stub:
            result = self.run_cli("commit", "--base-url", stub.url, "--dry-run")
        self.assertEqual(stub.call_count, 0)
        self.assertEqual(result.returncode, 0)
        self.assertIn("app.py", result.stdout)


class PrCommandTest(CliTestBase):
    def test_prints_pr_title_and_body_sections(self):
        self.change_file()
        with StubAPI(responses=[PR_OK]) as stub:
            result = self.run_cli("pr", "--base-url", stub.url)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PR Title", result.stdout)
        self.assertIn("## Why", result.stdout)
        self.assertIn("## What", result.stdout)
        self.assertIn("## How to Test", result.stdout)

    def test_shows_current_branch(self):
        self.change_file()
        with StubAPI(responses=[PR_OK]) as stub:
            result = self.run_cli("pr", "--base-url", stub.url)
        self.assertIn("feature/demo", result.stdout)

    def test_warns_when_section_still_missing_after_retry(self):
        self.change_file()
        incomplete = "TITLE: 제목\nBODY:\n## Why\n- 이유만 있음\n"
        with StubAPI(responses=[incomplete]) as stub:
            result = self.run_cli("pr", "--base-url", stub.url)
        self.assertIn("[WARN]", result.stdout)
        self.assertIn("How to Test", result.stdout)


class ErrorCaseTest(CliTestBase):
    def test_no_changes_exits_zero_with_message(self):
        with StubAPI() as stub:
            result = self.run_cli("commit", "--base-url", stub.url)
        self.assertEqual(result.returncode, 0)
        self.assertIn("변경 사항이 없습니다", result.stdout)
        self.assertEqual(stub.call_count, 0)

    def test_missing_api_key_exits_one_with_guidance(self):
        self.change_file()
        result = self.run_cli("commit", key=None)
        self.assertEqual(result.returncode, 1)
        self.assertIn("AI_API_KEY", result.stdout + result.stderr)

    def test_auth_failure_exits_two_with_reason(self):
        self.change_file()
        with StubAPI(status=401) as stub:
            result = self.run_cli("commit", "--base-url", stub.url)
        self.assertEqual(result.returncode, 2)
        self.assertIn("인증", result.stdout + result.stderr)

    def test_network_failure_exits_two(self):
        self.change_file()
        result = self.run_cli("commit", "--base-url", "http://127.0.0.1:1/v1", "--timeout", "2")
        self.assertEqual(result.returncode, 2)

    def test_outside_git_repository_exits_one(self):
        with tempfile.TemporaryDirectory() as plain:
            result = self.run_cli("commit", cwd=plain)
        self.assertEqual(result.returncode, 1)
        self.assertIn("git", (result.stdout + result.stderr).lower())

    def test_env_file_supplies_key(self):
        self.change_file()
        (self.repo / ".env").write_text("AI_API_KEY=from-env-file\n", encoding="utf8")
        with StubAPI(responses=[COMMIT_OK]) as stub:
            result = self.run_cli("commit", "--api-format", "openai", "--base-url", stub.url, key=None)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(stub.requests[0]["headers"]["Authorization"], "Bearer from-env-file")




class ModelCapabilityTest(CliTestBase):
    def test_warns_and_drops_temperature_for_gpt5_model(self):
        self.change_file()
        with StubAPI(responses=[COMMIT_OK]) as stub:
            result = self.run_cli("commit", "--api-format", "openai", "--base-url", stub.url,
                                  "--model", "gpt-5.5", "--temperature", "0.3")
        self.assertNotIn("temperature", stub.requests[0]["json"])
        self.assertIn("[WARN]", result.stdout)
        self.assertIn("temperature", result.stdout)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_does_not_warn_for_model_supporting_temperature(self):
        self.change_file()
        with StubAPI(responses=[COMMIT_OK]) as stub:
            result = self.run_cli("commit", "--api-format", "openai", "--base-url", stub.url,
                                  "--model", "gpt-4o-mini", "--temperature", "0.3")
        self.assertEqual(stub.requests[0]["json"]["temperature"], 0.3)
        self.assertNotIn("temperature 변경", result.stdout)


class StagedOptionTest(CliTestBase):
    def test_staged_without_staged_changes_does_not_call_api(self):
        self.change_file()  # 수정만 하고 git add 는 하지 않았다
        with StubAPI(responses=[COMMIT_OK]) as stub:
            result = self.run_cli("commit", "--staged", "--base-url", stub.url)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(stub.call_count, 0)
        self.assertIn("스테이징된 변경 사항이 없습니다", result.stdout)
        self.assertIn("git add", result.stdout)

    def test_staged_sends_only_staged_files(self):
        self.change_file()
        git(self.repo, "add", "app.py")
        (self.repo / "extra.py").write_text("x = 1\n", encoding="utf8")
        with StubAPI(responses=[COMMIT_OK]) as stub:
            result = self.run_cli("commit", "--staged", "--base-url", stub.url)
        self.assertEqual(result.returncode, 0, result.stderr)
        prompt = next(m["content"] for m in stub.requests[0]["json"]["messages"] if m["role"] == "user")
        self.assertIn("app.py", prompt)
        self.assertNotIn("extra.py", prompt)


class AnthropicFormatCliTest(CliTestBase):
    def test_default_is_anthropic_format_with_claude_sonnet_4(self):
        # 옵션·환경변수 없이 실행하면 Anthropic 형식 + claude-sonnet-4 로 요청한다
        self.change_file()
        with StubAPI(responses=[COMMIT_OK]) as stub:
            result = self.run_cli("commit", "--base-url", stub.url)
        self.assertEqual(result.returncode, 0, result.stderr)
        request = stub.requests[0]
        headers = {k.lower(): v for k, v in request["headers"].items()}
        self.assertEqual(request["path"], "/v1/messages")
        self.assertEqual(request["json"]["model"], "claude-sonnet-4")
        self.assertEqual(headers["x-api-key"], "test-key")

    def test_openai_format_is_still_available(self):
        self.change_file()
        with StubAPI(responses=[COMMIT_OK]) as stub:
            result = self.run_cli("commit", "--api-format", "openai", "--base-url", stub.url)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(stub.requests[0]["path"], "/v1/chat/completions")
        self.assertEqual(stub.requests[0]["json"]["model"], "gpt-5.5")
        # 실측한 PR 출력 최대(1159토큰)보다 넉넉해야 PR 이 잘리지 않는다
        self.assertEqual(stub.requests[0]["json"]["max_tokens"], 2000)

    def test_anthropic_format_uses_messages_api_and_claude_defaults(self):
        self.change_file()
        with StubAPI(responses=[COMMIT_OK], api_format="anthropic") as stub:
            result = self.run_cli("commit", "--api-format", "anthropic", "--base-url", stub.url)
        self.assertEqual(result.returncode, 0, result.stderr)
        request = stub.requests[0]
        self.assertEqual(request["path"], "/v1/messages")
        self.assertEqual(request["json"]["model"], "claude-sonnet-4")
        self.assertEqual(request["json"]["max_tokens"], 16000)
        # 기본 모델은 temperature 를 실제로 적용하는 모델이다 — 지정한 값이 그대로 전달돼야 한다
        self.assertEqual(request["json"]["temperature"], 0.2)
        self.assertNotIn("temperature 변경", result.stdout)
        self.assertIn("feat: 변경 사항 요약 기능 추가", result.stdout)
        self.assertIn("format=anthropic", result.stdout)

    def test_temperature_is_ignored_notice_for_opus_4_8(self):
        # claude-opus-4-7/4-8 은 temperature 를 지원하지 않는다 — 빼고 보내고 [WARN] 으로 알린다
        self.change_file()
        with StubAPI(responses=[COMMIT_OK], api_format="anthropic") as stub:
            result = self.run_cli("commit", "--api-format", "anthropic", "--base-url", stub.url,
                                  "--model", "claude-opus-4-8", "--temperature", "0.7")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("temperature", stub.requests[0]["json"])
        self.assertIn("[WARN]", result.stdout)

    def test_env_file_can_select_anthropic_format(self):
        self.change_file()
        (self.repo / ".env").write_text("AI_API_KEY=from-env-file\nAI_API_FORMAT=anthropic\n", encoding="utf8")
        with StubAPI(responses=[PR_OK], api_format="anthropic") as stub:
            result = self.run_cli("pr", "--base-url", stub.url, key=None)
        self.assertEqual(result.returncode, 0, result.stderr)
        headers = {k.lower(): v for k, v in stub.requests[0]["headers"].items()}
        self.assertEqual(headers["x-api-key"], "from-env-file")
        self.assertIn("## How to Test", result.stdout)

    def test_anthropic_api_key_env_is_accepted(self):
        self.change_file()
        with StubAPI(responses=[COMMIT_OK], api_format="anthropic") as stub:
            result = self.run_cli("commit", "--api-format", "anthropic", "--base-url", stub.url,
                                  key=None, extra_env={"ANTHROPIC_API_KEY": "anthropic-key"})
        self.assertEqual(result.returncode, 0, result.stderr)
        headers = {k.lower(): v for k, v in stub.requests[0]["headers"].items()}
        self.assertEqual(headers["x-api-key"], "anthropic-key")

    def test_retry_keeps_system_prompt_and_alternating_roles(self):
        self.change_file()
        with StubAPI(responses=["feat: " + "가" * 100, COMMIT_OK], api_format="anthropic") as stub:
            result = self.run_cli("commit", "--api-format", "anthropic", "--base-url", stub.url)
        self.assertEqual(result.returncode, 0, result.stderr)
        retry = stub.requests[1]["json"]
        self.assertIn("커밋 메시지", retry["system"])
        self.assertEqual([m["role"] for m in retry["messages"]], ["user", "assistant", "user"])

    def test_invalid_format_value_exits_one(self):
        self.change_file()
        result = self.run_cli("commit", extra_env={"AI_API_FORMAT": "gemini"})
        self.assertEqual(result.returncode, 1)
        self.assertIn("AI_API_FORMAT", result.stdout + result.stderr)


class OptionValidationTest(CliTestBase):
    def test_rejects_temperature_out_of_format_range_before_calling_api(self):
        # anthropic 형식은 0~1, openai 형식은 0~2 — 범위 밖이면 API 를 부르지 않고 사용 오류(1)로 끝낸다
        self.change_file()
        cases = (("anthropic", "1.5"), ("anthropic", "-0.1"), ("openai", "2.5"))
        for api_format, value in cases:
            with StubAPI(responses=[COMMIT_OK], api_format=api_format) as stub:
                result = self.run_cli("commit", "--api-format", api_format, "--base-url", stub.url,
                                      "--temperature", value)
            self.assertEqual(result.returncode, 1, (api_format, value))
            self.assertEqual(stub.call_count, 0, (api_format, value))
            self.assertIn("temperature", result.stderr, (api_format, value))

    def test_accepts_temperature_within_format_range(self):
        self.change_file()
        for api_format, value in (("anthropic", "1.0"), ("openai", "1.5")):
            with StubAPI(responses=[COMMIT_OK], api_format=api_format) as stub:
                result = self.run_cli("commit", "--api-format", api_format, "--base-url", stub.url,
                                      "--model", "claude-sonnet-4" if api_format == "anthropic" else "gpt-4o-mini",
                                      "--temperature", value)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(stub.requests[0]["json"]["temperature"], float(value))

    def test_rejects_non_positive_limits(self):
        # 잘못된 옵션은 사용 오류(1)다 — 2 는 API 오류용이다
        for option in ("--max-lines", "--max-files", "--max-tokens", "--timeout"):
            result = self.run_cli("commit", option, "0", "--dry-run")
            self.assertEqual(result.returncode, 1, option)
            self.assertIn("1 이상", result.stderr, option)

    def test_unknown_command_is_usage_error(self):
        result = self.run_cli("push")
        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid choice", result.stderr)


class TruncationTest(CliTestBase):
    """max_tokens 에 걸려 잘린 응답 — 형식 검증을 통과해도 경고하고, 재생성으로 호출을 낭비하지 않는다."""

    def test_warns_when_commit_is_cut_but_still_passes_format(self):
        self.change_file()
        body = json.dumps({"content": [{"type": "text", "text": "feat: 기능 추가\n\n- app.py 의 출력 문구를 바꾸"}],
                           "stop_reason": "max_tokens"})
        with StubAPI(body=body) as stub:
            result = self.run_cli("commit", "--base-url", stub.url, "--max-tokens", "30")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("max_tokens(30)에 걸려 중간에 잘렸습니다", result.stdout)

    def test_does_not_retry_truncated_response(self):
        self.change_file()
        body = json.dumps({"content": [{"type": "text", "text": "TITLE: 기능 추가\nBODY:\n## Why\n- 이유가 길어서 잘"}],
                           "stop_reason": "max_tokens"})
        with StubAPI(body=body) as stub:
            result = self.run_cli("pr", "--base-url", stub.url, "--max-tokens", "40")
        self.assertEqual(stub.call_count, 1)  # 섹션이 빠졌어도 같은 상한으로는 또 잘리므로 다시 부르지 않는다
        self.assertIn("잘렸습니다", result.stdout)
        self.assertIn("## What 섹션이 없습니다", result.stdout)

    def test_openai_finish_reason_length_is_reported(self):
        self.change_file()
        body = json.dumps({"choices": [{"message": {"content": "feat: 기능 추가\n\n- app.py 수"},
                                        "finish_reason": "length"}]})
        with StubAPI(body=body) as stub:
            result = self.run_cli("commit", "--api-format", "openai", "--base-url", stub.url)
        self.assertIn("잘렸습니다", result.stdout)

    def test_does_not_claim_to_send_omitted_temperature(self):
        self.change_file()
        with StubAPI(responses=[COMMIT_OK]) as stub:
            result = self.run_cli("commit", "--api-format", "openai", "--base-url", stub.url, "--model", "gpt-5.5")
        self.assertIn("temperature=모델 기본값", result.stdout)


if __name__ == "__main__":
    unittest.main()
