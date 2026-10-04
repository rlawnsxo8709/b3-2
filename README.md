# aicommit — AI Git 커밋/PR 메시지 생성기 (b3-2)

> `git status` · `git diff` 결과를 AI API로 보내 **커밋 메시지**와 **PR 초안**을 만들어 주는 터미널 도구.
> 외부 라이브러리 없이 **표준 라이브러리만**으로 구현했다.

| | |
|---|---|
| 실행 | `python main.py commit` / `python main.py pr` |
| 개발 환경 | Python 3.10 이상 (검증: 3.13.11, Linux) |
| 외부 라이브러리 | **없음** (`urllib.request`로 REST 호출) |
| API | OpenAI Chat Completions 호환 (`POST {base}/chat/completions`) · Anthropic Messages (`POST {base}/messages`) — `--api-format`으로 선택 |
| 기본 주소 | `https://copa.codyssey.kr/v1` (`--base-url`로 변경) |
| 기본 모델 | openai 형식 `gpt-5.5` · anthropic 형식 `claude-opus-4-8` (`--model`로 변경) |

설계 결정은 [PLAN.md](PLAN.md)에 있다.

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
| `AI_API_KEY` (또는 `OPENAI_API_KEY` / anthropic 형식이면 `ANTHROPIC_API_KEY`) | 인증 키. 없으면 안내 메시지와 함께 종료(코드 1) |
| `AI_API_BASE_URL` (또는 `OPENAI_BASE_URL`) | 호출 주소. 기본값 `https://copa.codyssey.kr/v1` |
| `AI_API_FORMAT` | 요청 형식 `openai`(기본) 또는 `anthropic`. `--api-format`이 우선한다 |

OpenAI 공식 API나 다른 호환 게이트웨이를 쓴다면 주소만 바꾸면 된다. 코드 수정은 필요 없다.

```bash
export AI_API_BASE_URL="https://api.openai.com/v1"
# 또는
python3 main.py commit --base-url https://api.openai.com/v1 --model gpt-4o-mini
```

### Anthropic 형식으로 요청하기

게이트웨이가 발급한 키가 OpenAI 호환 엔드포인트에서 거부되면(`This API key is not allowed for the OpenAI-compatible API`) Anthropic 형식으로 요청한다.
요청 경로·헤더·본문이 Messages API 규격으로 바뀐다.

| | openai 형식 | anthropic 형식 |
|---|---|---|
| 경로 | `POST {base}/chat/completions` | `POST {base}/messages` |
| 인증 헤더 | `Authorization: Bearer <key>` | `x-api-key: <key>` + `anthropic-version: 2023-06-01` |
| system 프롬프트 | `messages[0]`(role=system) | 최상위 `system` 필드 |
| 응답 | `choices[0].message.content` | `content` 블록 중 `type: "text"`만 이어 붙인다 |
| 기본 모델 · max_tokens | `gpt-5.5` · 700 | `claude-opus-4-8` · 16000 |

```bash
python3 main.py commit --api-format anthropic
# 매번 옵션을 붙이기 싫다면 .env 에 한 줄 추가
echo 'AI_API_FORMAT=anthropic' >> .env
# Anthropic 공식 API 로 최신 모델을 쓸 때
python3 main.py commit --api-format anthropic --base-url https://api.anthropic.com/v1 --model claude-opus-5-5
```

- 기본 게이트웨이가 제공하는 Claude 모델은 `claude-opus-4-8`, `claude-opus-4-7`, `claude-sonnet-4`, `claude-haiku-4`다(2026-10-04 `GET /v1/models` 기준). 목록에 없는 모델을 지정하면 `HTTP 404 (Model not found.)`로 끝난다.
- `max_tokens`는 생성 길이의 **상한**이고 실제 생성한 만큼만 과금된다. Claude 최신 모델은 사고(thinking) 토큰도 이 상한에 포함되므로 기본값을 넉넉히 두었다.
- 모델이 안전 정책으로 요청을 거절하면(HTTP 200 + `stop_reason: "refusal"`) 결과를 지어내지 않고 `[ERROR] 모델이 요청을 거절했습니다`로 종료(코드 2)한다. `claude-opus-5-5` 등 최신 모델에는 Anthropic 공식 API의 server-side fallback(`fallbacks: "default"`)을 함께 보내 거절 시 서버가 다른 모델로 한 번 더 시도하게 한다.

## 명령과 옵션

```bash
python3 main.py commit [옵션]   # 커밋 메시지 생성
python3 main.py pr     [옵션]   # PR 제목·본문 초안 생성
```

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--api-format` | `openai` | 요청 형식 `openai` / `anthropic` ([위](#anthropic-형식으로-요청하기) 참고) |
| `--model` | `gpt-5.5` (anthropic: `claude-opus-4-8`) | 사용할 모델 |
| `--temperature` | `0.2` | 높을수록 표현이 다양해지고 낮을수록 일관적이다. **모델이 지원할 때만 적용된다**(아래 참고) |
| `--max-tokens` | `700` (anthropic: `16000`) | 응답 최대 길이 |
| `--base-url` | `https://copa.codyssey.kr/v1` | API 주소 |
| `--timeout` | `30` | 요청 제한 시간(초) |
| `--staged` | 꺼짐 | 스테이징된 변경만 사용(`git diff --cached`). 스테이징한 것이 없으면 API를 호출하지 않고 종료한다 |
| `--no-safe-mode` | — | 마스킹·분량 제한 해제 (기본은 켜짐) |
| `--max-files` | `10` | safe-mode에서 보낼 최대 파일 수 |
| `--max-lines` | `200` | safe-mode에서 보낼 최대 diff 줄 수 |
| `--no-retry` | — | 형식 위반 시 재생성(2번째 호출)을 하지 않는다 |
| `--dry-run` | — | API를 호출하지 않고 보낼 프롬프트만 출력한다 (Key 불필요) |

숫자 옵션(`--max-tokens`, `--timeout`, `--max-files`, `--max-lines`)은 1 이상의 정수만 받는다.

사용 예시:

```bash
python3 main.py commit                          # 기본값으로 커밋 메시지 생성
python3 main.py commit --staged                 # 스테이징한 변경만 요약
python3 main.py commit --temperature 0.7        # 표현을 더 다양하게
python3 main.py pr --model claude-sonnet-4 --max-tokens 1200
python3 main.py commit --dry-run                # 어떤 프롬프트가 나가는지 먼저 확인
```

### 모델별 파라미터 제약

GPT-5·o 계열(`gpt-5.5`, `gpt-5-mini`, `o3-mini` 등)은 **`temperature` 변경을 받지 않는다.** 기본값이 아닌 값을 보내면 공급자가 요청을 거부한다.
그래서 이 도구는 해당 모델에서는 `temperature`를 요청 본문에서 빼고 호출하며, 그 사실을 로그로 알린다.

```
[INFO] gpt-5.5 모델은 temperature 변경을 지원하지 않습니다. 지정한 0.2 대신 모델 기본값으로 호출합니다.
```

Claude 4.7 이후 세대(`claude-opus-4-7`, `claude-opus-4-8`, `claude-opus-5-5`, `claude-sonnet-5-5` 등)는 `temperature`를 **아예 받지 않는다**(기본값 1도 거부). 이 모델들에는 `temperature`를 빼고, 대신 `output_config.effort`를 `low`로 보내 짧은 요약 작업에 맞게 사고 깊이와 비용을 줄인다.

`--temperature`를 직접 지정했는데 그 모델이 지원하지 않으면 `[WARN]`으로 알린다. 이때 요청 로그에는 `temperature=모델 기본값`으로 표시된다. 그 밖의 Claude(`claude-sonnet-4`, `claude-haiku-4`)·Gemini·GPT-4 계열은 지정한 값이 그대로 적용된다.

## 출력 예시

### 커밋 메시지 (`python3 main.py commit`)

아래는 이 저장소에서 실제로 실행한 결과다. (게이트웨이 `copa.codyssey.kr`, 모델 `gpt-5.5`)

```
[INFO] Git status 수집 완료: 5개 파일 변경 감지
[INFO] Git diff 수집 완료: 170줄 (민감정보 마스킹 적용)
[INFO] gpt-5.5 모델은 temperature 변경을 지원하지 않습니다. 지정한 0.2 대신 모델 기본값으로 호출합니다.
[INFO] AI API 요청 중... (model=gpt-5.5, temperature=0.2, max_tokens=700)
[DONE] 커밋 메시지 생성 완료 (API 호출 1회)
------------------------------------------------------------
--- Commit Message ---
fix: 고정 temperature 모델 요청 실패 방지

- aicommit/config.py에서 기본 모델과 기본 API URL을 갱신하고 temperature 지원 여부 판단을 추가
- aicommit/client.py에서 gpt-5·o 계열에 기본값이 아닌 temperature를 보내지 않도록 payload 생성 분리
- aicommit/cli.py에서 지원하지 않는 temperature 지정 시 사용자에게 안내 메시지 출력
- tests/test_client.py와 tests/test_cli_e2e.py에 모델별 temperature 처리 검증 추가
------------------------------------------------------------
```

### PR 초안 (`python3 main.py pr`)

같은 변경 사항으로 실행한 실제 결과다.

```
[INFO] Git status 수집 완료: 5개 파일 변경 감지
[INFO] Git diff 수집 완료: 170줄 (민감정보 마스킹 적용)
[INFO] 현재 브랜치: feature/gateway-model-support
[INFO] gpt-5.5 모델은 temperature 변경을 지원하지 않습니다. 지정한 0.2 대신 모델 기본값으로 호출합니다.
[INFO] AI API 요청 중... (model=gpt-5.5, temperature=0.2, max_tokens=700)
[DONE] PR 초안 생성 완료 (API 호출 1회)
------------------------------------------------------------
--- PR Title ---
게이트웨이 기본 모델 지원 및 temperature 처리 개선
------------------------------------------------------------
------------------------------------------------------------
--- PR Body ---
## Why
- 기본 API 엔드포인트와 모델을 게이트웨이 환경에 맞게 변경해야 합니다.
- GPT-5 및 o 계열 모델은 기본값이 아닌 temperature 파라미터를 거부하므로 요청 실패를 방지해야 합니다.
## What
- 기본 모델을 gpt-5.5로, 기본 base URL을 https://copa.codyssey.kr/v1로 변경했습니다.
- 모델별 temperature 변경 지원 여부를 판별하는 설정을 추가했습니다.
- temperature 변경을 지원하지 않는 모델에는 기본값이 아닌 temperature를 요청 본문에서 제외하도록 했습니다.
- CLI에서 지원하지 않는 temperature 값이 지정된 경우 사용자에게 안내 메시지를 출력하도록 했습니다.
- client payload 생성 및 CLI E2E 테스트를 추가했습니다.
## How to Test
- pytest로 전체 테스트를 실행합니다.
- gpt-5.5 모델에 temperature 0.3을 지정해 실행했을 때 요청 payload에 temperature가 없는지 확인합니다.
- gpt-4o-mini 모델에 temperature 0.3을 지정해 실행했을 때 요청 payload에 temperature가 포함되는지 확인합니다.
------------------------------------------------------------
```

### Anthropic 형식 (`python3 main.py commit --api-format anthropic`)

Anthropic 형식 지원을 추가한 변경 사항으로 실제 실행한 결과다. (게이트웨이 `copa.codyssey.kr`, 모델 `claude-opus-4-8`)

```
[INFO] Git status 수집 완료: 13개 파일 변경 감지
[INFO] Git diff 수집 완료: 838줄 (민감정보 마스킹 적용, 파일 3개 생략, 638줄 생략)
[INFO] claude-opus-4-8 모델은 temperature 변경을 지원하지 않습니다. 지정한 0.2 대신 모델 기본값으로 호출합니다.
[INFO] AI API 요청 중... (format=anthropic, model=claude-opus-4-8, temperature=모델 기본값, max_tokens=16000)
[DONE] 커밋 메시지 생성 완료 (API 호출 1회)
------------------------------------------------------------
--- Commit Message ---
feat: Anthropic Messages API 요청 형식 지원 추가

- client.py에 build_anthropic_payload와 api_format 분기를 추가해 /messages 요청과 system 필드 분리, effort·fallback 옵션을 처리
- config.py와 cli.py에 --api-format 옵션, 형식별 DEFAULT_MODELS·DEFAULT_MAX_TOKENS 기본값과 resolve_api_format·sends_temperature 로직을 도입
- cli.py에 _positive_int 검증과 스테이징 변경 없음 안내 메시지를 보강하고, stub_server 및 테스트 전반을 신규 형식에 맞게 갱신
------------------------------------------------------------
```

### 변경 사항이 없을 때

```
[INFO] 변경 사항이 없습니다. 생성하지 않고 종료합니다.
```

`--staged`인데 `git add`한 것이 없을 때도 API를 호출하지 않는다.

```
[INFO] 스테이징된 변경 사항이 없습니다. git add 로 올린 뒤 다시 실행하거나 --staged 없이 실행해 주세요.
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

> 생성 문구는 변경 내용과 모델에 따라 달라진다. 형식(제목 1줄, 불릿, 세 섹션)은 검증으로 보장한다.

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

- **마스킹**: OpenAI/Anthropic 계열 키(`sk-…`), AWS Access Key(`AKIA…`), GitHub 토큰(`ghp_…`), `Authorization: Bearer …`, 이름이 KEY·TOKEN·SECRET·PASSWORD·AUTH 등으로 **끝나는** 변수의 값(`API_KEY`, `db_password`, `apiKey`, `"x-api-key":` …), 이메일, `-----BEGIN … PRIVATE KEY-----` 블록 → `***MASKED***`
- 민감 단어가 이름 중간에 들어 있을 뿐인 변수(`author`, `monkey_count`, `token_count`, `max_tokens`)는 가리지 않는다. 비밀값이 아닌 코드까지 가려 AI가 변경 맥락을 잃지 않도록 하기 위해서다
- **분량 제한**: 파일 10개, diff 200줄까지만 전송하고 생략된 양을 로그로 알려 준다
- 값만 가리고 변수 이름은 남겨서 변경 맥락은 유지한다
- 추적되지 않은 새 파일(`??`)은 **이름만** 전송되고 내용은 전송되지 않는다(`git diff`에 나타나지 않기 때문). 새 파일 내용까지 요약하게 하려면 `git add` 후 실행한다
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
| `1` | 환경·사용 오류 — API Key 없음, git 저장소 아님, 알 수 없는 `AI_API_FORMAT` 값 |
| `2` | API 오류 — 인증 실패, 요청 한도 초과, 네트워크 실패, 응답 형식 오류, 모델의 요청 거절 |

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
│   ├── client.py        REST 호출(openai/anthropic 형식), 오류 분류, 호출 횟수
│   ├── validate.py      파싱 · 규칙 검증 · 후처리
│   ├── render.py        구분선·헤더 출력
│   └── errors.py        예외와 종료 코드
├── tests/               단위 + E2E 테스트 (표준 unittest)
├── README.md  PLAN.md
```

## 요구사항 체크리스트

**Git 변경 사항 수집**

- [x] Git 저장소 루트에서 실행 (아니면 안내 후 종료 코드 1) — `aicommit/gitctx.py:67`
- [x] `git status` 결과로 변경 파일 목록 수집 — `aicommit/gitctx.py:74`
- [x] `git diff` 결과로 변경 내용 수집 (`--staged` 지원) — `aicommit/gitctx.py:80-85`
- [x] 변경 없음 → "변경 사항이 없습니다" 출력 후 종료 — `aicommit/cli.py:109`

**AI API 연동**

- [x] API Key는 환경변수로만 사용, 하드코딩 없음 — `aicommit/config.py:81`
- [x] 실행 시 API 호출 후 생성 결과를 터미널에 출력 — `aicommit/cli.py:160`
- [x] 호출 실패 시 원인을 포함한 메시지 (인증/한도/404/네트워크/응답 형식/거절) — `aicommit/client.py:108`
- [x] 모델·temperature·max_tokens를 CLI 옵션으로 변경 가능, 기본값 존재 — `aicommit/cli.py:63`
- [x] OpenAI 호환 · Anthropic Messages 두 요청 형식 지원 — `aicommit/client.py:72`

**커밋 메시지 자동 생성**

- [x] `commit` 명령으로 커밋 메시지 생성·출력
- [x] 변경 사항 요약 기반, 제목 1줄 필수
- [x] 본문 포함 시 변경 파일 언급 또는 핵심 변경 불릿 (프롬프트 규칙 + 불릿 검증)
- [x] 복사해 쓸 수 있도록 구분선으로 구획해 출력 — `aicommit/render.py:25`

**PR 제목/본문 자동 생성**

- [x] `pr` 명령으로 PR 초안 생성
- [x] 본문에 `## Why` / `## What` / `## How to Test` 헤더 포함
- [x] 각 섹션 불릿 1개 이상 검증 — `aicommit/validate.py:120`
- [x] PR 제목 1줄 출력

**출력 형식 검증 및 다듬기**

- [x] 커밋 제목 50자 권장 · 72자 최대, PR 제목 80자 최대
- [x] 검증 후 **재생성**과 **후처리**를 모두 적용 — `aicommit/cli.py:85`
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
python3 -m unittest discover -s tests -t .     # 112개 통과
```

| 종류 | 검사 대상 |
|---|---|
| `test_sanitize.py` | 키·토큰·비밀번호·이메일·개인키 마스킹, camelCase·JSON 키·복수형 이름, 변수명 보존, 민감 단어를 포함만 한 이름(`author`, `max_tokens`) 미변경, 파일/줄 상한 |
| `test_gitctx.py` | **임시 git 저장소를 실제로 만들어** 변경 없음·수정·추적되지 않은 파일·스테이징(스테이징한 것만, 없으면 변경 없음)·커밋 없는 저장소·비(非)저장소 |
| `test_validate.py` | 제목/본문 파싱, 코드펜스 제거, 길이·섹션·불릿 검증, 후처리(단어 경계에서 자르기), 없는 섹션을 지어내지 않음 |
| `test_prompts.py` | 변경 파일·diff·브랜치·출력 규칙이 프롬프트에 포함되는지 |
| `test_client.py` | **로컬 스텁 HTTP 서버**로 요청 파라미터·헤더·경로, 응답 파싱, 401/429/500/잘못된 JSON/타임아웃/연결 실패, 호출 횟수, anthropic 형식(경로·`x-api-key`·system 분리·text 블록만 추출·temperature/effort·거절·max_tokens 소진) |
| `test_cli_e2e.py` | 실제 git 저장소 + 스텁 서버로 `main.py` 실행 — commit/pr 출력, 파라미터 전달, 재생성, safe-mode, dry-run, 변경 없음, `--staged` 빈 스테이징, Key 없음, 인증 실패, 저장소 아님, `.env` 읽기, `--api-format anthropic`·`AI_API_FORMAT`, 숫자 옵션 검증 |

테스트는 mock 라이브러리를 쓰지 않는다. git은 실제 임시 저장소로, API는 실제 HTTP 스텁 서버로 검증한다.

**실제 API 호출 검증** — 게이트웨이(`https://copa.codyssey.kr/v1`, 모델 `gpt-5.5`)로 `commit`과 `pr`을 각각 실행해 정상 동작을 확인했다. 위 [출력 예시](#출력-예시)가 그 결과다.

| 확인 항목 | 결과 |
|---|---|
| `GET /v1/models` | 사용 가능 모델 11종 확인 (gpt-5.5, gpt-5-mini, claude-*, gemini-* 등) |
| `commit` 실호출 | API 호출 1회, 제목 72자 이내, 불릿 4개 |
| `pr` 실호출 | API 호출 1회, 세 섹션 헤더와 섹션별 불릿 충족 |
| GPT-5 계열 `temperature` | 기본값이 아닌 값 전송 시 공급자 오류 → 요청 본문에서 제외하도록 처리 |
| anthropic 형식 `commit`·`pr` 실호출 (2026-10-04) | `POST /v1/messages`, 모델 `claude-opus-4-8`, 각각 API 호출 1회, 형식 규칙 충족 |
| anthropic 형식 `claude-opus-5-5` | 게이트웨이에 없는 모델 → `HTTP 404 (Model not found.)` 오류로 안내 |
