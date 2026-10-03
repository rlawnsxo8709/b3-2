"""생성 결과 파싱 · 규칙 검증 · 후처리."""

import unittest

from aicommit.validate import (
    COMMIT_TITLE_MAX,
    PR_TITLE_MAX,
    fix_commit,
    fix_pr,
    parse_commit,
    parse_pr,
    validate_commit,
    validate_pr,
)

GOOD_COMMIT = """feat: 커밋 메시지 자동 생성 기능 추가

- git diff 수집 로직 추가 (gitctx.py)
- 프롬프트 템플릿 적용 (prompts.py)
"""

GOOD_PR = """TITLE: feat: 커밋/PR 자동 생성 기능 추가
BODY:
## Why
- 커밋 메시지 작성 시간을 줄이기 위해

## What
- git diff 수집과 AI 호출 연결

## How to Test
- python main.py commit 실행
"""


class ParseCommitTest(unittest.TestCase):
    def test_splits_title_and_body(self):
        msg = parse_commit(GOOD_COMMIT)
        self.assertEqual(msg.title, "feat: 커밋 메시지 자동 생성 기능 추가")
        self.assertIn("- git diff 수집 로직 추가", msg.body)

    def test_title_only(self):
        msg = parse_commit("fix: 오타 수정")
        self.assertEqual(msg.title, "fix: 오타 수정")
        self.assertEqual(msg.body, "")

    def test_strips_code_fence_from_model_output(self):
        msg = parse_commit("```\nfix: 오타 수정\n```")
        self.assertEqual(msg.title, "fix: 오타 수정")

    def test_ignores_leading_blank_lines(self):
        self.assertEqual(parse_commit("\n\nfix: 오타 수정").title, "fix: 오타 수정")


class ValidateCommitTest(unittest.TestCase):
    def test_good_message_has_no_violation(self):
        self.assertEqual(validate_commit(parse_commit(GOOD_COMMIT)), [])

    def test_empty_title_is_violation(self):
        self.assertTrue(validate_commit(parse_commit("")))

    def test_title_over_max_is_violation(self):
        msg = parse_commit("feat: " + "가" * 100)
        violations = validate_commit(msg)
        self.assertTrue(any(str(COMMIT_TITLE_MAX) in v for v in violations))

    def test_body_without_bullet_is_violation(self):
        msg = parse_commit("feat: 기능 추가\n\n그냥 설명 문장입니다.")
        self.assertTrue(validate_commit(msg))

    def test_fix_truncates_long_title(self):
        fixed = fix_commit(parse_commit("feat: " + "가" * 100))
        self.assertLessEqual(len(fixed.title), COMMIT_TITLE_MAX)
        self.assertEqual(validate_commit(fixed), [])


class ParsePrTest(unittest.TestCase):
    def test_parses_title_and_body(self):
        pr = parse_pr(GOOD_PR)
        self.assertEqual(pr.title, "feat: 커밋/PR 자동 생성 기능 추가")
        self.assertIn("## Why", pr.body)
        self.assertIn("## How to Test", pr.body)

    def test_parses_without_markers(self):
        pr = parse_pr("feat: 제목만 먼저\n## Why\n- 이유\n## What\n- 변경\n## How to Test\n- 실행")
        self.assertEqual(pr.title, "feat: 제목만 먼저")
        self.assertIn("## Why", pr.body)


class ValidatePrTest(unittest.TestCase):
    def test_good_pr_has_no_violation(self):
        self.assertEqual(validate_pr(parse_pr(GOOD_PR)), [])

    def test_missing_section_is_violation(self):
        pr = parse_pr("TITLE: 제목\nBODY:\n## Why\n- 이유\n## What\n- 변경")
        violations = validate_pr(pr)
        self.assertTrue(any("How to Test" in v for v in violations))

    def test_section_without_bullet_is_violation(self):
        pr = parse_pr("TITLE: 제목\nBODY:\n## Why\n설명만 있음\n## What\n- 변경\n## How to Test\n- 실행")
        self.assertTrue(any("Why" in v for v in validate_pr(pr)))

    def test_title_over_max_is_violation(self):
        pr = parse_pr(f"TITLE: {'가' * 100}\nBODY:\n## Why\n- a\n## What\n- b\n## How to Test\n- c")
        self.assertTrue(any(str(PR_TITLE_MAX) in v for v in validate_pr(pr)))

    def test_fix_truncates_long_title(self):
        pr = parse_pr(f"TITLE: {'가' * 100}\nBODY:\n## Why\n- a\n## What\n- b\n## How to Test\n- c")
        self.assertLessEqual(len(fix_pr(pr).title), PR_TITLE_MAX)

    def test_fix_cannot_invent_missing_section(self):
        # 없는 내용을 지어내지 않는다 — 위반은 경고로 남아야 한다
        pr = parse_pr("TITLE: 제목\nBODY:\n## Why\n- 이유")
        self.assertTrue(validate_pr(fix_pr(pr)))


if __name__ == "__main__":
    unittest.main()
