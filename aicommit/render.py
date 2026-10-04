"""터미널 출력 — 로그와 결과물을 구분선으로 나눠 보여준다."""

import sys

SEPARATOR = "-" * 60


# 로그는 바로 내보낸다 — 출력을 파이프로 받을 때 stderr 의 [ERROR] 가 앞선 로그보다 먼저 찍히지 않게 한다
def info(text):
    print(f"[INFO] {text}", flush=True)


def done(text):
    print(f"[DONE] {text}", flush=True)


def warn(text):
    print(f"[WARN] {text}", flush=True)


def error(text):
    print(f"[ERROR] {text}", file=sys.stderr)


def block(title, body):
    """결과물을 구분선과 헤더로 감싼 한 덩어리로 만든다."""
    return f"{SEPARATOR}\n--- {title} ---\n{body.rstrip()}\n{SEPARATOR}"


def commit_block(message):
    return block("Commit Message", message.text())


def pr_block(pr):
    return block("PR Title", pr.title) + "\n" + block("PR Body", pr.body)
