"""safe-mode: 민감정보 마스킹 + diff 분량 제한."""

import unittest

from aicommit.sanitize import mask_secrets, limit_diff, sanitize_diff

DIFF_HEAD = "diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n"


class MaskSecretsTest(unittest.TestCase):
    def assert_masked(self, text, secret):
        masked = mask_secrets(text)
        self.assertNotIn(secret, masked)
        self.assertIn("***MASKED***", masked)

    def test_openai_key(self):
        self.assert_masked("+key = 'sk-proj-abcd1234EFGH5678ijkl'", "sk-proj-abcd1234EFGH5678ijkl")

    def test_aws_access_key(self):
        self.assert_masked("+AWS_KEY=AKIAIOSFODNN7EXAMPLE", "AKIAIOSFODNN7EXAMPLE")

    def test_github_token(self):
        self.assert_masked("+token: ghp_0123456789abcdefghijABCDEFGHIJ0123", "ghp_0123456789abcdefghijABCDEFGHIJ0123")

    def test_bearer_token(self):
        self.assert_masked('+headers = {"Authorization": "Bearer abcdef0123456789xyz"}', "abcdef0123456789xyz")

    def test_env_assignment(self):
        self.assert_masked("+DATABASE_PASSWORD=sup3r-s3cret-value", "sup3r-s3cret-value")

    def test_email(self):
        self.assert_masked("+문의: hong.gildong@example.com", "hong.gildong@example.com")

    def test_private_key_block(self):
        text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA1234\n-----END RSA PRIVATE KEY-----"
        self.assert_masked(text, "MIIEowIBAAKCAQEA1234")

    def test_keeps_variable_name_as_context(self):
        # 값만 가리고 변수 이름은 남겨야 AI가 변경 맥락을 이해할 수 있다
        self.assertIn("DATABASE_PASSWORD", mask_secrets("+DATABASE_PASSWORD=sup3r-s3cret"))

    def test_normal_code_is_untouched(self):
        code = "+def add(a, b):\n+    return a + b"
        self.assertEqual(mask_secrets(code), code)

    def test_camel_case_secret_name(self):
        self.assert_masked('+const apiKey = "abcd1234efgh5678";', "abcd1234efgh5678")

    def test_quoted_json_key(self):
        self.assert_masked('+  "password": "hunter2hunter2",', "hunter2hunter2")

    def test_plural_secret_name(self):
        self.assert_masked("+API_KEYS=abcd1234,efgh5678", "abcd1234,efgh5678")

    def test_header_style_name(self):
        self.assert_masked("+x-api-key: abcd1234efgh5678", "abcd1234efgh5678")

    def test_names_merely_containing_secret_words_are_untouched(self):
        # 민감 단어가 이름의 '마지막 단어'일 때만 가린다 — author(auth), monkey(key), max_tokens 는 그대로 둔다
        code = "\n".join([
            '+author = "Kim"',
            '+keyboard_layout = "qwerty"',
            "+monkey_count = 3",
            "+token_count = len(tokens)",
            "+DEFAULT_MAX_TOKENS = 700",
            '+    payload = {"max_tokens": max_tokens}',
        ])
        self.assertEqual(mask_secrets(code), code)


class LimitDiffTest(unittest.TestCase):
    def make_diff(self, files, lines_per_file):
        parts = []
        for i in range(files):
            body = "\n".join(f"+line {n}" for n in range(lines_per_file))
            parts.append(f"diff --git a/f{i}.py b/f{i}.py\n{body}")
        return "\n".join(parts)

    def test_keeps_small_diff_as_is(self):
        diff = self.make_diff(2, 3)
        result = limit_diff(diff, max_files=10, max_lines=200)
        self.assertEqual(result.text, diff)
        self.assertEqual((result.omitted_files, result.omitted_lines), (0, 0))

    def test_limits_number_of_files(self):
        result = limit_diff(self.make_diff(12, 2), max_files=10, max_lines=500)
        self.assertEqual(result.text.count("diff --git"), 10)
        self.assertEqual(result.omitted_files, 2)

    def test_limits_number_of_lines(self):
        result = limit_diff(self.make_diff(1, 300), max_files=10, max_lines=200)
        self.assertEqual(len(result.text.splitlines()), 200)
        self.assertEqual(result.omitted_lines, 101)  # 헤더 1줄 + 본문 300줄 = 301줄

    def test_notes_omission_in_text(self):
        result = limit_diff(self.make_diff(12, 2), max_files=10, max_lines=500)
        self.assertIn("생략", result.note)


class SanitizeDiffTest(unittest.TestCase):
    def test_safe_mode_masks_and_limits(self):
        diff = DIFF_HEAD + "+API_KEY=sk-proj-abcd1234EFGH5678ijkl\n" + "\n".join(f"+line {n}" for n in range(300))
        result = sanitize_diff(diff, safe_mode=True, max_files=10, max_lines=50)
        self.assertNotIn("sk-proj-abcd1234EFGH5678ijkl", result.text)
        self.assertLessEqual(len(result.text.splitlines()), 50)
        self.assertTrue(result.masked)

    def test_safe_mode_off_sends_diff_as_is(self):
        diff = DIFF_HEAD + "+API_KEY=sk-proj-abcd1234EFGH5678ijkl"
        result = sanitize_diff(diff, safe_mode=False, max_files=10, max_lines=200)
        self.assertEqual(result.text, diff)
        self.assertFalse(result.masked)


if __name__ == "__main__":
    unittest.main()
