"""생성 결과 파싱 · 규칙 검증 · 후처리.

AI 출력은 그대로 믿지 않는다. 규칙을 코드로 검사하고,
고칠 수 있는 것(길이)은 자동으로 다듬고, 없는 내용(누락된 섹션)은 지어내지 않고 경고로 알린다.
"""

import re
from dataclasses import dataclass

COMMIT_TITLE_RECOMMENDED = 50
COMMIT_TITLE_MAX = 72
PR_TITLE_MAX = 80
PR_SECTIONS = ("## Why", "## What", "## How to Test")

_FENCE = re.compile(r"^\s*```[a-zA-Z]*\s*\n(.*?)\n?\s*```\s*$", re.S)


@dataclass
class CommitMessage:
    title: str
    body: str = ""

    def text(self):
        return f"{self.title}\n\n{self.body}".rstrip() if self.body else self.title


@dataclass
class PullRequest:
    title: str
    body: str = ""


def _strip_fence(text):
    match = _FENCE.match(text.strip())
    return match.group(1) if match else text.strip()


def _has_bullet(text):
    return any(line.strip().startswith("- ") for line in text.splitlines())


def parse_commit(text):
    """모델 출력에서 제목 1줄과 본문을 분리한다."""
    cleaned = _strip_fence(text)
    lines = cleaned.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines:
        return CommitMessage(title="", body="")
    return CommitMessage(title=lines[0].strip(), body="\n".join(lines[1:]).strip())


def validate_commit(message):
    """규칙 위반 목록을 돌려준다. 비어 있으면 통과."""
    violations = []
    if not message.title:
        violations.append("커밋 제목이 비어 있습니다.")
    elif len(message.title) > COMMIT_TITLE_MAX:
        violations.append(f"커밋 제목이 {COMMIT_TITLE_MAX}자를 넘습니다. (현재 {len(message.title)}자)")
    if message.body and not _has_bullet(message.body):
        violations.append('커밋 본문에 "- " 로 시작하는 불릿이 없습니다.')
    return violations


def fix_commit(message):
    """고칠 수 있는 위반만 손본다 — 제목 길이."""
    title = message.title
    if len(title) > COMMIT_TITLE_MAX:
        title = title[:COMMIT_TITLE_MAX].rstrip()
    return CommitMessage(title=title, body=message.body)


def parse_pr(text):
    """TITLE:/BODY: 규약을 우선 적용하고, 없으면 첫 줄을 제목으로 본다."""
    cleaned = _strip_fence(text)
    title, body_lines, body_started = "", [], False

    for line in cleaned.splitlines():
        stripped = line.strip()
        if not body_started:
            if stripped.upper().startswith("TITLE:"):
                title = stripped[len("TITLE:"):].strip()
                continue
            if stripped.upper() == "BODY:":
                body_started = True
                continue
            if not title and stripped and not stripped.startswith("#"):
                title = stripped
                continue
            if stripped:
                body_started = True
        body_lines.append(line)

    return PullRequest(title=title, body="\n".join(body_lines).strip())


def _section_text(body, section):
    """해당 섹션 헤더부터 다음 헤더 직전까지의 본문."""
    lines = body.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip().lower() == section.lower())
    except StopIteration:
        return None
    collected = []
    for line in lines[start + 1:]:
        if line.strip().startswith("## "):
            break
        collected.append(line)
    return "\n".join(collected)


def validate_pr(pr):
    """PR 제목 길이와 세 섹션(헤더 + 불릿)을 검사한다."""
    violations = []
    if not pr.title:
        violations.append("PR 제목이 비어 있습니다.")
    elif len(pr.title) > PR_TITLE_MAX:
        violations.append(f"PR 제목이 {PR_TITLE_MAX}자를 넘습니다. (현재 {len(pr.title)}자)")

    for section in PR_SECTIONS:
        body = _section_text(pr.body, section)
        if body is None:
            violations.append(f"{section} 섹션이 없습니다.")
        elif not _has_bullet(body):
            violations.append(f'{section} 섹션에 "- " 불릿이 없습니다.')
    return violations


def fix_pr(pr):
    """고칠 수 있는 위반만 손본다 — 제목 길이. 없는 섹션은 지어내지 않는다."""
    title = pr.title
    if len(title) > PR_TITLE_MAX:
        title = title[:PR_TITLE_MAX].rstrip()
    return PullRequest(title=title, body=pr.body)
