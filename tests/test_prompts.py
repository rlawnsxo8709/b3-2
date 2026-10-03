"""프롬프트 구성 — 변경 맥락과 출력 규칙이 모두 들어가야 한다."""

import unittest

from aicommit.gitctx import GitContext
from aicommit.prompts import build_commit_messages, build_pr_messages, retry_instruction

CTX = GitContext(
    branch="feature/commit-pr-generator",
    changed_files=["aicommit/cli.py", "README.md"],
    untracked_files=["README.md"],
    status="M  aicommit/cli.py\n?? README.md",
    diff="diff --git a/aicommit/cli.py b/aicommit/cli.py\n+def main():\n+    return 0",
)


class CommitPromptTest(unittest.TestCase):
    def setUp(self):
        self.messages = build_commit_messages(CTX, CTX.diff)
        self.joined = "\n".join(m["content"] for m in self.messages)

    def test_has_system_and_user_roles(self):
        self.assertEqual([m["role"] for m in self.messages], ["system", "user"])

    def test_includes_changed_files_and_diff(self):
        self.assertIn("aicommit/cli.py", self.joined)
        self.assertIn("+def main():", self.joined)

    def test_states_title_length_rule(self):
        self.assertIn("50", self.joined)
        self.assertIn("72", self.joined)

    def test_asks_for_bullet_body(self):
        self.assertIn("- ", self.joined)


class PrPromptTest(unittest.TestCase):
    def setUp(self):
        self.messages = build_pr_messages(CTX, CTX.diff)
        self.joined = "\n".join(m["content"] for m in self.messages)

    def test_includes_branch_name(self):
        self.assertIn("feature/commit-pr-generator", self.joined)

    def test_requires_three_sections(self):
        for section in ("## Why", "## What", "## How to Test"):
            self.assertIn(section, self.joined)

    def test_states_title_length_rule(self):
        self.assertIn("80", self.joined)

    def test_defines_output_markers(self):
        self.assertIn("TITLE:", self.joined)
        self.assertIn("BODY:", self.joined)


class RetryInstructionTest(unittest.TestCase):
    def test_lists_violations(self):
        text = retry_instruction(["제목이 72자를 넘습니다.", "## How to Test 섹션이 없습니다."])
        self.assertIn("72자", text)
        self.assertIn("How to Test", text)


if __name__ == "__main__":
    unittest.main()
