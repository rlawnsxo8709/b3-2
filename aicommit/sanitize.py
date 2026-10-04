"""safe-mode — diff 를 외부 API 로 보내기 전에 손본다.

두 가지를 함께 한다.
  (A) 마스킹   : 키·토큰·비밀번호·이메일·개인키처럼 보이는 값을 ***MASKED*** 로 바꾼다
  (B) 분량 제한: 파일 수와 줄 수를 제한해 과도한 전송과 비용을 막는다
값만 가리고 변수 이름은 남겨서, AI 가 변경 맥락은 그대로 이해할 수 있게 한다.
"""

import re
from dataclasses import dataclass

MASK = "***MASKED***"
# 민감 단어가 이름의 '마지막 단어'일 때만 비밀값 이름으로 본다.
#   잡는다  : API_KEY, API_KEYS, db_password, x-api-key, self.secret, apiKey, githubToken, TOKEN2
#   놔둔다  : author(auth), monkey_count(key), token_count, max_tokens(LLM 파라미터라 tokens 복수형은 제외)
_SECRET_WORD = "keys?|token|secrets?|passwords?|passwd|pwd|credentials?|auth"
_SECRET_WORD_CAMEL = "Keys?|Token|Secrets?|Passwords?|Passwd|Pwd|Credentials?|Auth"
SECRET_NAME = (
    rf"(?:(?:[A-Za-z0-9]+[_.-])*(?i:{_SECRET_WORD})"   # 구분자(_ . -)로 나뉜 이름
    rf"|[A-Za-z0-9]*[a-z0-9](?:{_SECRET_WORD_CAMEL})"  # camelCase 이름
    r")\d*(?![A-Za-z0-9_])"
)

# 순서대로 적용한다. 개인키 블록처럼 범위가 넓은 것을 먼저 지운다.
PATTERNS = (
    # -----BEGIN ... PRIVATE KEY----- ... -----END ... PRIVATE KEY-----
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
     f"-----BEGIN PRIVATE KEY----- {MASK} -----END PRIVATE KEY-----"),
    # OpenAI / Anthropic 계열 키
    (re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"), MASK),
    # AWS Access Key ID
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), MASK),
    # GitHub 토큰
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), MASK),
    # Authorization: Bearer <토큰>
    (re.compile(r"(?i)\b(Bearer)\s+[A-Za-z0-9._~+/=-]{8,}"), rf"\1 {MASK}"),
    # API_KEY=값 / password: "값" / "api_key": "값" — 이름은 남기고 값만 가린다
    # (대소문자 무시는 SECRET_NAME 안에서만 건다. 전체에 걸면 camelCase 경계가 사라져 monkey 도 잡힌다)
    (re.compile(rf"(?m)^(\s*[+-]?\s*['\"]?{SECRET_NAME}['\"]?\s*[:=]\s*)\S.*$"), rf"\1{MASK}"),
    (re.compile(rf"\b({SECRET_NAME}['\"]?)(\s*[:=]\s*)['\"]?[A-Za-z0-9._~+/=-]{{6,}}['\"]?"), rf"\1\2{MASK}"),
    # 이메일
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), MASK),
)


@dataclass
class LimitResult:
    text: str
    omitted_files: int = 0
    omitted_lines: int = 0
    note: str = ""


@dataclass
class SanitizeResult:
    text: str
    masked: bool = False
    omitted_files: int = 0
    omitted_lines: int = 0
    note: str = ""


def mask_secrets(text):
    """민감정보로 보이는 값을 MASK 로 치환한다."""
    for pattern, replacement in PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _split_files(diff):
    """diff 를 파일 단위 조각으로 나눈다."""
    if not diff.strip():
        return []
    sections, current = [], []
    for line in diff.splitlines():
        if line.startswith("diff --git") and current:
            sections.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append("\n".join(current))
    return sections


def limit_diff(diff, max_files, max_lines):
    """파일 수와 줄 수 상한을 적용한다."""
    sections = _split_files(diff)
    omitted_files = max(0, len(sections) - max_files)
    kept = sections[:max_files]
    text = "\n".join(kept)

    lines = text.splitlines()
    total_lines = len(diff.splitlines())
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        text = "\n".join(lines)
    omitted_lines = max(0, total_lines - len(lines))

    notes = []
    if omitted_files:
        notes.append(f"파일 {omitted_files}개 생략")
    if omitted_lines:
        notes.append(f"{omitted_lines}줄 생략")
    return LimitResult(text=text, omitted_files=omitted_files, omitted_lines=omitted_lines, note=", ".join(notes))


def sanitize_diff(diff, *, safe_mode=True, max_files, max_lines):
    """safe-mode 가 켜져 있으면 마스킹 후 분량을 제한한다."""
    if not safe_mode:
        return SanitizeResult(text=diff)

    masked_text = mask_secrets(diff)
    limited = limit_diff(masked_text, max_files=max_files, max_lines=max_lines)
    return SanitizeResult(
        text=limited.text,
        masked=masked_text != diff,
        omitted_files=limited.omitted_files,
        omitted_lines=limited.omitted_lines,
        note=limited.note,
    )
