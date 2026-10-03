"""git status/diff 수집 — 임시 저장소를 실제로 만들어 검사한다 (mock 없음)."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from aicommit.errors import NotAGitRepository
from aicommit.gitctx import collect


def git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


class GitContextTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "config", "user.email", "test@example.com")
        git(self.repo, "config", "user.name", "test")
        (self.repo / "app.py").write_text("print('hello')\n", encoding="utf8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "init")

    def tearDown(self):
        self._tmp.cleanup()

    def test_clean_repo_has_no_changes(self):
        ctx = collect(self.repo)
        self.assertFalse(ctx.has_changes)
        self.assertEqual(ctx.changed_files, [])

    def test_collects_branch_name(self):
        self.assertEqual(collect(self.repo).branch, "main")

    def test_detects_modified_file_with_diff(self):
        (self.repo / "app.py").write_text("print('hi')\n", encoding="utf8")
        ctx = collect(self.repo)
        self.assertTrue(ctx.has_changes)
        self.assertIn("app.py", ctx.changed_files)
        self.assertIn("+print('hi')", ctx.diff)

    def test_detects_untracked_file(self):
        (self.repo / "new.py").write_text("x = 1\n", encoding="utf8")
        ctx = collect(self.repo)
        self.assertTrue(ctx.has_changes)
        self.assertIn("new.py", ctx.changed_files)
        self.assertIn("new.py", ctx.untracked_files)

    def test_staged_option_collects_only_staged_changes(self):
        (self.repo / "app.py").write_text("print('staged')\n", encoding="utf8")
        git(self.repo, "add", "app.py")
        (self.repo / "other.py").write_text("y = 2\n", encoding="utf8")
        ctx = collect(self.repo, staged=True)
        self.assertIn("+print('staged')", ctx.diff)
        self.assertNotIn("y = 2", ctx.diff)

    def test_default_includes_unstaged_changes(self):
        (self.repo / "app.py").write_text("print('unstaged')\n", encoding="utf8")
        self.assertIn("+print('unstaged')", collect(self.repo).diff)

    def test_repository_without_commits(self):
        with tempfile.TemporaryDirectory() as empty:
            git(empty, "init", "-q", "-b", "main")
            (Path(empty) / "a.txt").write_text("a\n", encoding="utf8")
            ctx = collect(Path(empty))
            self.assertTrue(ctx.has_changes)
            self.assertIn("a.txt", ctx.changed_files)

    def test_non_git_directory_raises(self):
        with tempfile.TemporaryDirectory() as plain:
            with self.assertRaises(NotAGitRepository):
                collect(Path(plain))

    def test_diff_line_count_is_reported(self):
        (self.repo / "app.py").write_text("print('a')\nprint('b')\n", encoding="utf8")
        ctx = collect(self.repo)
        self.assertEqual(ctx.diff_line_count, len(ctx.diff.splitlines()))


if __name__ == "__main__":
    unittest.main()
