# aicommit — AI Git 커밋/PR 메시지 생성기 (b3-2)

> `git status` · `git diff` 결과를 AI API로 보내 **커밋 메시지**와 **PR 초안**을 만들어 주는 터미널 도구.
> 외부 라이브러리 없이 **표준 라이브러리만**으로 구현했다.

| | |
|---|---|
| 실행 | `python main.py commit` / `python main.py pr` |
| 개발 환경 | Python 3.10 이상 (검증: 3.13.11, Linux) |
| 외부 라이브러리 | **없음** (`urllib.request`로 REST 호출) |
| API | OpenAI Chat Completions 호환 (`POST {base}/chat/completions`) |
| 기본 모델 | `gpt-4o-mini` (`--model`로 변경) |

설계 결정은 [PLAN.md](PLAN.md), 과제 목표 답변은 [EXPLAIN.md](EXPLAIN.md)에 있다.

---

## 목차

1. [설치 및 실행](#설치-및-실행)
2. [API Key 설정](#api-key-설정)
3. [명령과 옵션](#명령과-옵션)
4. [출력 예시](#출력-예시)
5. [동작 흐름](#동작-흐름)
6. [민감정보와 비용 — 주의사항](#민감정보와-비용--주의사항)
7. [종료 코드](#종료-코드)
8. [폴더 구조](#폴더-구조)
9. [요구사항 체크리스트](#요구사항-체크리스트)
10. [검증](#검증)

---

## 설치 및 실행

설치 과정이 없다. Python 3.10 이상이면 내려받아 바로 실행한다.

```bash
git clone https://github.com/rlawnsxo8709/b3-2.git
cd b3-2
python3 main.py --help
```

이 도구는 **Git 저장소 루트에서** 실행한다. 다른 프로젝트에서 쓰려면 이 폴더의 경로를 지정해 실행한다.

```bash
cd ~/my-project          # 변경 사항이 있는 내 프로젝트
python3 ~/b3-2/main.py commit
```

`python -m aicommit commit` 형태로도 같은 기능을 실행할 수 있다.

## API Key 설정

Key는 **환경변수로만** 받는다. 코드에 하드코딩하지 않으며, 저장소의 `.gitignore`가 `.env`를 막는다.

```bash
# 방법 1 — 환경변수
export AI_API_KEY="YOUR_KEY"

# 방법 2 — 실행 디렉토리의 .env 파일 (이미 설정된 환경변수를 덮어쓰지 않는다)
echo 'AI_API_KEY=YOUR_KEY' > .env
```

| 환경변수 | 용도 |
|---|---|
| `AI_API_KEY` (또는 `OPENAI_API_KEY`) | 인증 키. 없으면 안내 메시지와 함께 종료(코드 1) |
| `AI_API_BASE_URL` (또는 `OPENAI_BASE_URL`) | 호출 주소. 기본값 `https://api.openai.com/v1` |

OpenAI 호환 게이트웨이를 쓴다면 주소만 바꾸면 된다. 코드 수정은 필요 없다.

```bash
export AI_API_BASE_URL="https://my-gateway.example.com/v1"
# 또는
python3 main.py commit --base-url https://my-gateway.example.com/v1
```

## 명령과 옵션

```bash
python3 main.py commit [옵션]   # 커밋 메시지 생성
python3 main.py pr     [옵션]   # PR 제목·본문 초안 생성
```

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--model` | `gpt-4o-mini` | 사용할 모델 |
| `--temperature` | `0.2` | 높을수록 표현이 다양해지고 낮을수록 일관적이다 |
| `--max-tokens` | `700` | 응답 최대 길이 |
| `--base-url` | OpenAI | API 주소 |
| `--timeout` | `30` | 요청 제한 시간(초) |
| `--staged` | 꺼짐 | 스테이징된 변경만 사용(`git diff --cached`) |
| `--no-safe-mode` | — | 마스킹·분량 제한 해제 (기본은 켜짐) |
| `--max-files` | `10` | safe-mode에서 보낼 최대 파일 수 |
| `--max-lines` | `200` | safe-mode에서 보낼 최대 diff 줄 수 |
| `--no-retry` | — | 형식 위반 시 재생성(2번째 호출)을 하지 않는다 |
| `--dry-run` | — | API를 호출하지 않고 보낼 프롬프트만 출력한다 (Key 불필요) |

사용 예시:

```bash
python3 main.py commit                          # 기본값으로 커밋 메시지 생성
python3 main.py commit --staged                 # 스테이징한 변경만 요약
python3 main.py commit --temperature 0.7        # 표현을 더 다양하게
python3 main.py pr --model gpt-4o --max-tokens 1200
python3 main.py commit --dry-run                # 어떤 프롬프트가 나가는지 먼저 확인
```

## 출력 예시

### 커밋 메시지 (`python3 main.py commit`)

```
[INFO] Git status 수집 완료: 3개 파일 변경 감지
[INFO] Git diff 수집 완료: 128줄 (민감정보 마스킹 적용)
[INFO] AI API 요청 중... (model=gpt-4o-mini, temperature=0.2, max_tokens=700)
[DONE] 커밋 메시지 생성 완료 (API 호출 1회)
------------------------------------------------------------
--- Commit Message ---
feat: Git 변경 사항 기반 커밋 메시지 자동 생성 기능 추가

- git status/diff 수집 로직 추가 (gitctx.py)
- 커밋 메시지 프롬프트와 출력 규칙 정의 (prompts.py)
- 제목 길이·불릿 검증 후 재생성 흐름 적용 (validate.py)
------------------------------------------------------------
```

### PR 초안 (`python3 main.py pr`)

```
[INFO] Git status 수집 완료: 3개 파일 변경 감지
[INFO] Git diff 수집 완료: 128줄 (민감정보 마스킹 적용)
[INFO] 현재 브랜치: feature/commit-pr-generator
[INFO] AI API 요청 중... (model=gpt-4o-mini, temperature=0.2, max_tokens=700)
[DONE] PR 초안 생성 완료 (API 호출 1회)
------------------------------------------------------------
--- PR Title ---
feat: 커밋/PR 자동 생성 기능 추가
------------------------------------------------------------
------------------------------------------------------------
--- PR Body ---
## Why
- 커밋 메시지와 PR 설명 작성에 시간이 들어 자동 생성 도구가 필요했다.

## What
- git status/diff 결과를 AI 입력 컨텍스트로 전달하는 로직 추가
- commit/pr 명령과 출력 형식 검증 추가

## How to Test
- export AI_API_KEY="YOUR_KEY"
- python3 main.py commit 실행 후 제목이 72자 이내인지 확인
------------------------------------------------------------
```

### 변경 사항이 없을 때

```
[INFO] 변경 사항이 없습니다. 생성하지 않고 종료합니다.
```

### API Key가 없을 때

```
[ERROR] AI_API_KEY 환경변수가 설정되지 않았습니다.
       예) export AI_API_KEY="YOUR_KEY"   또는 프로젝트 루트에 .env 파일 작성
```

### 형식 규칙을 지키지 못했을 때

1차 결과가 규칙을 어기면 위반 내용을 알려주고 **한 번만** 다시 생성한다. 그래도 남으면 경고로 표시하고, 없는 내용을 지어내지는 않는다.

```
[WARN] 형식 규칙 위반을 발견해 한 번 더 생성합니다: ## How to Test 섹션이 없습니다.
[DONE] PR 초안 생성 완료 (API 호출 2회)
[WARN] 형식 규칙을 만족하지 못했습니다 — ## How to Test 섹션이 없습니다. 직접 보완해 주세요.
```

> 위 출력은 형식 그대로의 예시다. 실제 문구는 변경 내용에 따라 달라진다.

## 동작 흐름

```
 git status --porcelain ─┐
                         ├─▶ GitContext ─▶ safe-mode(마스킹·분량 제한) ─▶ 프롬프트 구성 ─▶ AI API 호출(1회)
 git diff HEAD ──────────┘                                                                   │
                                                                                             ▼
  터미널 출력 ◀── 구분선·헤더로 구획 ◀── 후처리(길이 자르기) ◀── 규칙 검증 ─(위반 시 1회)─ 재생성
```

생성 규칙은 코드로 검사한다.

| 항목 | 규칙 |
|---|---|
| 커밋 제목 | 1줄, 50자 권장 · **72자 초과 금지** |
| 커밋 본문 | 선택. 포함하면 `- ` 불릿 1개 이상 |
| PR 제목 | 1줄, **80자 이내** |
| PR 본문 | `## Why` · `## What` · `## How to Test` 헤더 필수, 각 섹션 불릿 1개 이상 |

## 민감정보와 비용 — 주의사항

**민감정보**: `diff`에는 키나 비밀번호가 섞일 수 있다. safe-mode(기본 켜짐)가 전송 전에 다음을 처리한다.

- **마스킹**: OpenAI/Anthropic 계열 키(`sk-…`), AWS Access Key(`AKIA…`), GitHub 토큰(`ghp_…`), `Authorization: Bearer …`, `*_KEY`/`*_TOKEN`/`*_SECRET`/`*_PASSWORD` 형태의 값, 이메일, `-----BEGIN … PRIVATE KEY-----` 블록 → `***MASKED***`
- **분량 제한**: 파일 10개, diff 200줄까지만 전송하고 생략된 양을 로그로 알려 준다
- 값만 가리고 변수 이름은 남겨서 변경 맥락은 유지한다
- `--no-safe-mode`는 원본 diff를 그대로 보낸다. 사내 코드나 비밀값이 있다면 쓰지 않는 편이 안전하다
- 마스킹은 **보조 수단**이다. 애초에 비밀값을 커밋하지 않는 것이 먼저다

**비용과 요청 횟수**

- 한 번 실행에 API 호출 **1회**. 형식 위반이 있을 때만 **1회 더**(최대 2회) 호출한다
- 실제 호출 횟수를 `[DONE] … (API 호출 N회)`로 항상 출력한다
- `--no-retry`로 1회로 고정할 수 있고, `--dry-run`은 호출하지 않는다
- 큰 변경을 다룰 때는 `--max-lines`를 줄이면 토큰 사용량이 줄어든다
- 생성 결과는 **초안**이다. 사람이 검토한 뒤 사용한다. 이 도구는 `git commit`이나 PR 생성을 자동으로 수행하지 않는다

## 종료 코드

| 코드 | 상황 |
|---|---|
| `0` | 성공 (변경 사항 없음도 포함) |
| `1` | 환경·사용 오류 — API Key 없음, git 저장소 아님 |
| `2` | API 오류 — 인증 실패, 요청 한도 초과, 네트워크 실패, 응답 형식 오류 |

## 폴더 구조

```
.
├── main.py              python main.py commit 진입점
├── aicommit/
│   ├── cli.py           argparse 정의와 전체 흐름 조립
│   ├── config.py        기본값, 환경변수, .env 읽기
│   ├── gitctx.py        git status/diff 수집
│   ├── sanitize.py      safe-mode — 마스킹 + 분량 제한
│   ├── prompts.py       커밋/PR 프롬프트와 출력 규약
│   ├── client.py        REST 호출, 오류 분류, 호출 횟수
│   ├── validate.py      파싱 · 규칙 검증 · 후처리
│   ├── render.py        구분선·헤더 출력
│   └── errors.py        예외와 종료 코드
├── tests/               단위 + E2E 테스트 (표준 unittest)
├── README.md  PLAN.md  EXPLAIN.md
```

## 요구사항 체크리스트

**Git 변경 사항 수집**

- [x] Git 저장소 루트에서 실행 (아니면 안내 후 종료 코드 1) — `aicommit/gitctx.py:63`
- [x] `git status` 결과로 변경 파일 목록 수집 — `aicommit/gitctx.py:74`
- [x] `git diff` 결과로 변경 내용 수집 (`--staged` 지원) — `aicommit/gitctx.py:77-83`
- [x] 변경 없음 → "변경 사항이 없습니다" 출력 후 종료 — `aicommit/cli.py:83`

**AI API 연동**

- [x] API Key는 환경변수로만 사용, 하드코딩 없음 — `aicommit/config.py:50`
- [x] 실행 시 API 호출 후 생성 결과를 터미널에 출력 — `aicommit/cli.py:119`
- [x] 호출 실패 시 원인을 포함한 메시지 (인증/한도/404/네트워크/응답 형식) — `aicommit/client.py:54`
- [x] 모델·temperature·max_tokens를 CLI 옵션으로 변경 가능, 기본값 존재 — `aicommit/cli.py:39`

**커밋 메시지 자동 생성**

- [x] `commit` 명령으로 커밋 메시지 생성·출력
- [x] 변경 사항 요약 기반, 제목 1줄 필수
- [x] 본문 포함 시 변경 파일 언급 또는 핵심 변경 불릿 (프롬프트 규칙 + 불릿 검증)
- [x] 복사해 쓸 수 있도록 구분선으로 구획해 출력 — `aicommit/render.py:26`

**PR 제목/본문 자동 생성**

- [x] `pr` 명령으로 PR 초안 생성
- [x] 본문에 `## Why` / `## What` / `## How to Test` 헤더 포함
- [x] 각 섹션 불릿 1개 이상 검증 — `aicommit/validate.py:112`
- [x] PR 제목 1줄 출력

**출력 형식 검증 및 다듬기**

- [x] 커밋 제목 50자 권장 · 72자 최대, PR 제목 80자 최대
- [x] 검증 후 **재생성**과 **후처리**를 모두 적용 — `aicommit/cli.py:59`
- [x] 구분선·헤더로 구획해 출력

**리포지토리 및 문서화**

- [x] GitHub 저장소에 push
- [x] README에 설치·실행, 환경변수 설정, 사용 예시, 출력 예시 포함
- [x] 민감정보 대응과 비용·요청 횟수 안내 포함

**제약 사항**

- [x] 1회 실행당 API 호출 1~2회, 호출 횟수 로그 출력
- [x] Git 연동은 `status`/`diff`까지, 초안 출력까지만 — `git push`나 PR 자동 생성 없음
- [x] safe-mode 제공: 마스킹(A)과 분량 제한(B) 동시 적용

## 검증

```bash
python3 -m unittest discover -s tests -t .     # 79개 통과
```

| 종류 | 검사 대상 |
|---|---|
| `test_sanitize.py` | 키·토큰·비밀번호·이메일·개인키 마스킹, 변수명 보존, 일반 코드 미변경, 파일/줄 상한 |
| `test_gitctx.py` | **임시 git 저장소를 실제로 만들어** 변경 없음·수정·추적되지 않은 파일·스테이징·커밋 없는 저장소·비(非)저장소 |
| `test_validate.py` | 제목/본문 파싱, 코드펜스 제거, 길이·섹션·불릿 검증, 후처리, 없는 섹션을 지어내지 않음 |
| `test_prompts.py` | 변경 파일·diff·브랜치·출력 규칙이 프롬프트에 포함되는지 |
| `test_client.py` | **로컬 스텁 HTTP 서버**로 요청 파라미터·헤더·경로, 응답 파싱, 401/429/500/잘못된 JSON/타임아웃/연결 실패, 호출 횟수 |
| `test_cli_e2e.py` | 실제 git 저장소 + 스텁 서버로 `main.py` 실행 — commit/pr 출력, 파라미터 전달, 재생성, safe-mode, dry-run, 변경 없음, Key 없음, 인증 실패, 저장소 아님, `.env` 읽기 |

테스트는 mock 라이브러리를 쓰지 않는다. git은 실제 임시 저장소로, API는 실제 HTTP 스텁 서버로 검증한다.

> **실제 API 호출 검증**: 과제로 받은 키(`sk-cody-…`)는 OpenAI 엔드포인트에서 401을 반환해, 공개 API에 대한 실호출은 아직 확인하지 못했다.
> 유효한 키 또는 게이트웨이 주소를 받으면 `--base-url`만 지정해 바로 확인할 수 있다.
