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

    def test_staged_without_staged_changes_has_no_changes(self):
        # 수정만 하고 git add 하지 않았다면 --staged 로는 보낼 것이 없다
        (self.repo / "app.py").write_text("print('unstaged')\n", encoding="utf8")
        (self.repo / "new.py").write_text("x = 1\n", encoding="utf8")
        ctx = collect(self.repo, staged=True)
        self.assertFalse(ctx.has_changes)
        self.assertEqual(ctx.changed_files, [])

    def test_staged_lists_only_staged_files(self):
        (self.repo / "app.py").write_text("print('staged')\n", encoding="utf8")
        git(self.repo, "add", "app.py")
        (self.repo / "new.py").write_text("x = 1\n", encoding="utf8")
        ctx = collect(self.repo, staged=True)
        self.assertEqual(ctx.changed_files, ["app.py"])
        self.assertEqual(ctx.untracked_files, [])

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

    def test_non_utf8_file_does_not_crash(self):
        # CP949 로 저장된 파일이 diff 에 섞여도 멈추지 않는다 — 깨진 글자만 �로 바뀌고 나머지는 그대로다
        legacy = self.repo / "legacy.py"
        legacy.write_bytes("# 안녕\nx = 1\n".encode("cp949"))
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "legacy")
        legacy.write_bytes("# 반가워\nx = 2\n".encode("cp949"))
        ctx = collect(self.repo)
        self.assertIn("legacy.py", ctx.changed_files)
        self.assertIn("+x = 2", ctx.diff)
        self.assertIn("�", ctx.diff)

    def test_diff_line_count_is_reported(self):
        (self.repo / "app.py").write_text("print('a')\nprint('b')\n", encoding="utf8")
        ctx = collect(self.repo)
        self.assertEqual(ctx.diff_line_count, len(ctx.diff.splitlines()))


if __name__ == "__main__":
    unittest.main()
