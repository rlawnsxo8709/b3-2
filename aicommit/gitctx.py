"""Git 명령 결과를 프로그램 입력으로 연결하는 지점.

git status --porcelain → 변경 파일 목록
git diff (HEAD | --cached) → 변경 내용
둘 다 비어 있으면 '변경 사항 없음'으로 본다.
"""

import subprocess
from dataclasses import dataclass, field

from .errors import GitCommandError, NotAGitRepository


@dataclass
class GitContext:
    branch: str
    changed_files: list = field(default_factory=list)
    untracked_files: list = field(default_factory=list)
    status: str = ""
    diff: str = ""

    @property
    def has_changes(self):
        return bool(self.status.strip() or self.diff.strip())

    @property
    def diff_line_count(self):
        return len(self.diff.splitlines())

    @property
    def file_count(self):
        return len(self.changed_files)


def _run(repo_dir, *args, check=True):
    try:
        result = subprocess.run(
            ["git", *args], cwd=repo_dir, capture_output=True, text=True, encoding="utf8",
            errors="replace",  # CP949 등 UTF-8 이 아닌 파일이 diff 에 섞여도 멈추지 않는다 — 깨진 글자만 �로 바꾼다
        )
    except FileNotFoundError as exc:  # git 자체가 없는 환경
        raise GitCommandError("git 명령을 찾을 수 없습니다. git 설치 여부를 확인해 주세요.") from exc
    if check and result.returncode != 0:
        raise GitCommandError(f"git {' '.join(args)} 실패: {result.stderr.strip()}")
    return result


def _parse_status(status_text):
    """porcelain 출력에서 파일 경로를 뽑는다. 이름 변경은 새 경로를 쓴다."""
    changed, untracked = [], []
    for line in status_text.splitlines():
        if not line.strip():
            continue
        code, path = line[:2], line[3:].strip()
        if " -> " in path:  # R  old -> new
            path = path.split(" -> ", 1)[1]
        path = path.strip('"')
        changed.append(path)
        if code.strip() == "??":
            untracked.append(path)
    return changed, untracked


def collect(repo_dir=None, staged=False):
    """현재(또는 지정한) 디렉토리의 git 변경 사항을 모은다."""
    repo_dir = str(repo_dir) if repo_dir else None

    inside = _run(repo_dir, "rev-parse", "--is-inside-work-tree", check=False)
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        raise NotAGitRepository(
            "현재 디렉토리가 git 저장소가 아닙니다. git 저장소 루트에서 실행해 주세요."
        )

    branch = _run(repo_dir, "branch", "--show-current").stdout.strip() or "HEAD"
    status = _run(repo_dir, "status", "--porcelain").stdout
    if staged:
        # 첫 글자(스테이징 영역)에 변화가 있는 줄만 남긴다 — 작업 트리 수정(' M')과 추적되지 않은 파일('??')은 뺀다
        status = "".join(line for line in status.splitlines(keepends=True) if line[:1] not in (" ", "?"))
    changed, untracked = _parse_status(status)

    if staged:
        diff = _run(repo_dir, "diff", "--cached").stdout
    else:
        # 커밋이 하나도 없는 저장소에서는 HEAD 가 없으므로 스테이징 영역만 본다
        head = _run(repo_dir, "diff", "HEAD", check=False)
        diff = head.stdout if head.returncode == 0 else _run(repo_dir, "diff", "--cached").stdout

    return GitContext(
        branch=branch, changed_files=changed, untracked_files=untracked, status=status, diff=diff,
    )
