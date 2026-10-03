"""프롬프트 설계 — 결과 품질을 통제하는 핵심 부분.

세 가지를 함께 넣는다.
  1. 역할과 작성 규칙(system)  2. 변경 맥락: 브랜치·파일 목록·diff(user)  3. 출력 형식 규약
출력 형식을 글자로 못 박아 두어야 파싱과 검증이 가능해진다.
"""

from .validate import COMMIT_TITLE_MAX, COMMIT_TITLE_RECOMMENDED, PR_SECTIONS, PR_TITLE_MAX

COMMIT_SYSTEM = f"""너는 Git 커밋 메시지를 작성하는 시니어 개발자다.
주어진 변경 사항만 근거로 삼고, 확인되지 않은 내용은 지어내지 않는다.

작성 규칙
- 1번째 줄은 커밋 제목이다. {COMMIT_TITLE_RECOMMENDED}자 이내를 권장하고 {COMMIT_TITLE_MAX}자를 절대 넘기지 않는다.
- 제목은 Conventional Commits 형식을 쓴다. 예) feat: ..., fix: ..., docs: ..., refactor: ..., test: ...
- 제목 다음에는 빈 줄 하나를 두고 본문을 쓴다.
- 본문은 "- " 로 시작하는 불릿 2~4개로 쓰고, 변경된 파일이나 모듈 이름을 1~3개 언급한다.
- 한국어로 쓰고, 변경 이유와 핵심 변경 사항을 요약한다.
- 코드 블록(```)이나 다른 설명 문장은 쓰지 않는다. 커밋 메시지 본문만 출력한다."""

PR_SYSTEM = f"""너는 Pull Request 설명을 작성하는 시니어 개발자다.
주어진 변경 사항만 근거로 삼고, 확인되지 않은 내용은 지어내지 않는다.

출력 형식(반드시 지킨다)
TITLE: <PR 제목 한 줄, {PR_TITLE_MAX}자 이내>
BODY:
{PR_SECTIONS[0]}
- <변경 배경 1개 이상>
{PR_SECTIONS[1]}
- <핵심 변경 사항 1개 이상>
{PR_SECTIONS[2]}
- <테스트 방법 1개 이상>

작성 규칙
- 세 섹션 헤더를 그대로 쓰고, 각 섹션에 "- " 불릿을 1개 이상 넣는다.
- 한국어로 쓰고, 코드 블록(```)이나 그 밖의 설명 문장은 쓰지 않는다."""


def _context_block(ctx, diff_text):
    files = "\n".join(f"- {path}" for path in ctx.changed_files) or "- (없음)"
    untracked = ", ".join(ctx.untracked_files) or "없음"
    return (
        f"[브랜치] {ctx.branch}\n"
        f"[변경 파일 {len(ctx.changed_files)}개]\n{files}\n"
        f"[추적되지 않은 파일] {untracked}\n\n"
        f"[git status --porcelain]\n{ctx.status.strip() or '(없음)'}\n\n"
        f"[git diff]\n{diff_text.strip() or '(diff 없음 — 파일 목록만으로 요약한다)'}"
    )


def build_commit_messages(ctx, diff_text):
    """커밋 메시지 생성용 messages 배열."""
    return [
        {"role": "system", "content": COMMIT_SYSTEM},
        {"role": "user", "content": "아래 변경 사항에 대한 커밋 메시지를 작성해줘.\n\n" + _context_block(ctx, diff_text)},
    ]


def build_pr_messages(ctx, diff_text):
    """PR 제목·본문 생성용 messages 배열."""
    return [
        {"role": "system", "content": PR_SYSTEM},
        {"role": "user", "content": "아래 변경 사항에 대한 Pull Request 초안을 작성해줘.\n\n" + _context_block(ctx, diff_text)},
    ]


def retry_instruction(violations):
    """형식 위반을 알려주고 다시 작성하게 하는 추가 지시."""
    lines = "\n".join(f"- {item}" for item in violations)
    return (
        "직전 출력이 아래 규칙을 어겼다. 같은 변경 사항으로 형식만 고쳐서 다시 작성해라.\n"
        f"{lines}\n"
        "형식 외의 내용은 바꾸지 말고, 지정된 출력 형식만 지켜서 다시 출력해라."
    )
