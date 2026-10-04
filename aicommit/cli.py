"""CLI 진입점 — 수집 → 마스킹 → 호출 → 검증 → 출력 흐름을 조립한다."""

import argparse

from . import render
from .client import AIClient
from .config import (
    API_FORMAT_ENV,
    API_FORMATS,
    DEFAULT_BASE_URL,
    DEFAULT_MAX_FILES,
    DEFAULT_MAX_LINES,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODELS,
    DEFAULT_TEMPERATURE,
    PROVIDER_DEFAULT_TEMPERATURE,
    DEFAULT_TIMEOUT,
    apply_env_file,
    resolve_api_format,
    resolve_api_key,
    resolve_base_url,
    sends_temperature,
    supports_custom_temperature,
)
from .errors import AICommitError
from .gitctx import collect
from .prompts import build_commit_messages, build_pr_messages, retry_instruction
from .sanitize import sanitize_diff
from .validate import (
    COMMIT_TITLE_RECOMMENDED,
    fix_commit,
    fix_pr,
    parse_commit,
    parse_pr,
    validate_commit,
    validate_pr,
)


def _positive_int(value):
    try:
        number = int(value)
    except ValueError:
        number = 0
    if number < 1:
        raise argparse.ArgumentTypeError(f"1 이상의 정수여야 합니다: {value}")
    return number


def _per_format(values):
    return " / ".join(f"{name} {values[name]}" for name in API_FORMATS)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="aicommit",
        description="Git 변경 사항을 AI API 로 보내 커밋 메시지와 PR 초안을 생성한다.",
    )
    parser.add_argument("command", choices=("commit", "pr"), help="commit: 커밋 메시지 / pr: PR 제목·본문")
    parser.add_argument("--api-format", choices=API_FORMATS, default=None,
                        help=f"요청 형식 — openai: /chat/completions, anthropic: /messages "
                             f"(기본 openai, 환경변수 {API_FORMAT_ENV})")
    parser.add_argument("--model", default=None, help=f"사용할 모델 (기본 {_per_format(DEFAULT_MODELS)})")
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE,
                        help=f"다양성 조절 0.0~2.0 (기본 {DEFAULT_TEMPERATURE})")
    parser.add_argument("--max-tokens", type=_positive_int, default=None,
                        help=f"응답 최대 토큰 (기본 {_per_format(DEFAULT_MAX_TOKENS)})")
    parser.add_argument("--base-url", default=None,
                        help=f"API 주소 (기본 {DEFAULT_BASE_URL}, 환경변수 AI_API_BASE_URL)")
    parser.add_argument("--timeout", type=_positive_int, default=DEFAULT_TIMEOUT,
                        help=f"요청 제한 시간 초 (기본 {DEFAULT_TIMEOUT})")
    parser.add_argument("--staged", action="store_true", help="스테이징된 변경만 사용 (git diff --cached)")
    parser.add_argument("--no-safe-mode", dest="safe_mode", action="store_false",
                        help="민감정보 마스킹과 분량 제한을 끈다 (기본: 켜짐)")
    parser.add_argument("--max-files", type=_positive_int, default=DEFAULT_MAX_FILES,
                        help=f"safe-mode 에서 보낼 최대 파일 수 (기본 {DEFAULT_MAX_FILES})")
    parser.add_argument("--max-lines", type=_positive_int, default=DEFAULT_MAX_LINES,
                        help=f"safe-mode 에서 보낼 최대 diff 줄 수 (기본 {DEFAULT_MAX_LINES})")
    parser.add_argument("--no-retry", dest="retry", action="store_false",
                        help="형식 위반 시 재생성(2번째 호출)을 하지 않는다")
    parser.add_argument("--dry-run", action="store_true", help="API 를 호출하지 않고 보낼 프롬프트만 출력한다")
    return parser


def _generate(client, messages, args, parse, validate, fix):
    """1회 호출 → 검증 → (필요하면) 1회 재생성 → 후처리. 남은 위반을 함께 돌려준다."""
    text = client.complete(messages, model=args.model, temperature=args.temperature, max_tokens=args.max_tokens)
    result = parse(text)
    violations = validate(result)

    if violations and args.retry:
        render.warn("형식 규칙 위반을 발견해 한 번 더 생성합니다: " + "; ".join(violations))
        retry_messages = messages + [
            {"role": "assistant", "content": text},
            {"role": "user", "content": retry_instruction(violations)},
        ]
        text = client.complete(retry_messages, model=args.model, temperature=args.temperature,
                               max_tokens=args.max_tokens)
        result = parse(text)
        violations = validate(result)

    fixed = fix(result)
    return fixed, validate(fixed)


def _collect_context(args):
    """git 수집 + safe-mode 적용. 변경이 없으면 (None, None)."""
    ctx = collect(staged=args.staged)
    if not ctx.has_changes:
        if args.staged:
            render.info("스테이징된 변경 사항이 없습니다. git add 로 올린 뒤 다시 실행하거나 --staged 없이 실행해 주세요.")
        else:
            render.info("변경 사항이 없습니다. 생성하지 않고 종료합니다.")
        return None, None

    render.info(f"Git status 수집 완료: {ctx.file_count}개 파일 변경 감지")
    sanitized = sanitize_diff(ctx.diff, safe_mode=args.safe_mode, max_files=args.max_files, max_lines=args.max_lines)
    notes = []
    if sanitized.masked:
        notes.append("민감정보 마스킹 적용")
    if sanitized.note:
        notes.append(sanitized.note)
    suffix = f" ({', '.join(notes)})" if notes else ""
    render.info(f"Git diff 수집 완료: {ctx.diff_line_count}줄{suffix}")
    return ctx, sanitized


def _resolve_defaults(args):
    """형식에 따라 달라지는 기본값을 채운다. .env 를 읽은 뒤에 불러야 AI_API_FORMAT 이 반영된다."""
    args.api_format = resolve_api_format(args.api_format)
    args.model = args.model or DEFAULT_MODELS[args.api_format]
    args.max_tokens = args.max_tokens or DEFAULT_MAX_TOKENS[args.api_format]


def run(args):
    apply_env_file(".")
    _resolve_defaults(args)
    ctx, sanitized = _collect_context(args)
    if ctx is None:
        return 0

    is_commit = args.command == "commit"
    build = build_commit_messages if is_commit else build_pr_messages
    messages = build(ctx, sanitized.text)

    if not is_commit:
        render.info(f"현재 브랜치: {ctx.branch}")

    if args.dry_run:
        render.info("--dry-run: API 를 호출하지 않고 프롬프트만 출력합니다.")
        print(render.block("Prompt (system)", messages[0]["content"]))
        print(render.block("Prompt (user)", messages[1]["content"]))
        return 0

    if not supports_custom_temperature(args.model) and args.temperature != PROVIDER_DEFAULT_TEMPERATURE:
        notice = render.warn if args.temperature != DEFAULT_TEMPERATURE else render.info
        notice(f"{args.model} 모델은 temperature 변경을 지원하지 않습니다. "
               f"지정한 {args.temperature} 대신 모델 기본값으로 호출합니다.")

    client = AIClient(resolve_api_key(args.api_format), resolve_base_url(args.base_url),
                      timeout=args.timeout, api_format=args.api_format)
    temperature = args.temperature if sends_temperature(args.model, args.temperature) else "모델 기본값"
    render.info(f"AI API 요청 중... (format={args.api_format}, model={args.model}, "
                f"temperature={temperature}, max_tokens={args.max_tokens})")

    if is_commit:
        result, violations = _generate(client, messages, args, parse_commit, validate_commit, fix_commit)
        render.done(f"커밋 메시지 생성 완료 (API 호출 {client.calls}회)")
        if len(result.title) > COMMIT_TITLE_RECOMMENDED:
            render.warn(f"커밋 제목이 권장 {COMMIT_TITLE_RECOMMENDED}자를 넘습니다. (현재 {len(result.title)}자)")
        body = render.commit_block(result)
    else:
        result, violations = _generate(client, messages, args, parse_pr, validate_pr, fix_pr)
        render.done(f"PR 초안 생성 완료 (API 호출 {client.calls}회)")
        body = render.pr_block(result)

    for violation in violations:
        render.warn(f"형식 규칙을 만족하지 못했습니다 — {violation} 직접 보완해 주세요.")

    print(body)
    return 0


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except AICommitError as exc:
        render.error(str(exc))
        return exc.exit_code
