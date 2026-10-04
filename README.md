# aicommit — AI Git 커밋/PR 메시지 생성기 (b3-2)

> `git status` · `git diff` 결과를 AI API로 보내 **커밋 메시지**와 **PR 초안**을 만들어 주는 터미널 도구.
> 외부 라이브러리 없이 **표준 라이브러리만**으로 구현했다.

| | |
|---|---|
| 실행 | `python main.py commit` / `python main.py pr` |
| 개발 환경 | Python 3.10 이상 (검증: 3.13.11, Linux) |
| 외부 라이브러리 | **없음** (`urllib.request`로 REST 호출) |
| API | **Anthropic Messages**(`POST {base}/messages`, 기본) · OpenAI Chat Completions 호환(`POST {base}/chat/completions`) — `--api-format`으로 선택 |
| 기본 주소 | `https://copa.codyssey.kr/v1` (`--base-url`로 변경) |
| 기본 모델 | `claude-sonnet-4` (openai 형식이면 `gpt-5.5`, `--model`로 변경) |

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
| `AI_API_FORMAT` | 요청 형식 `anthropic`(기본) 또는 `openai`. `--api-format`이 우선한다 |

OpenAI 공식 API나 다른 OpenAI 호환 게이트웨이를 쓴다면 형식과 주소만 바꾸면 된다. 코드 수정은 필요 없다.

```bash
export AI_API_FORMAT=openai
export AI_API_BASE_URL="https://api.openai.com/v1"
# 또는
python3 main.py commit --api-format openai --base-url https://api.openai.com/v1 --model gpt-4o-mini
```

### 요청 형식

기본은 **Anthropic Messages 형식**이다. 기본 게이트웨이가 발급한 키는 OpenAI 호환 엔드포인트에서 거부되기 때문이다(`This API key is not allowed for the OpenAI-compatible API`).
OpenAI 호환 키·게이트웨이를 쓸 때만 `--api-format openai`(또는 `AI_API_FORMAT=openai`)를 지정한다. 형식에 따라 요청 경로·헤더·본문이 바뀐다.

| | openai 형식 | anthropic 형식 |
|---|---|---|
| 경로 | `POST {base}/chat/completions` | `POST {base}/messages` |
| 인증 헤더 | `Authorization: Bearer <key>` | `x-api-key: <key>` + `anthropic-version: 2023-06-01` |
| system 프롬프트 | `messages[0]`(role=system) | 최상위 `system` 필드 |
| 응답 | `choices[0].message.content` | `content` 블록 중 `type: "text"`만 이어 붙인다 |
| 기본 모델 · max_tokens | `gpt-5.5` · 2000 | `claude-sonnet-4` · 16000 |

```bash
python3 main.py commit                      # 기본: anthropic 형식 + claude-sonnet-4
python3 main.py commit --api-format openai  # OpenAI 호환 형식 + gpt-5.5
# Anthropic 공식 API 로 최신 모델을 쓸 때
python3 main.py commit --base-url https://api.anthropic.com/v1 --model claude-opus-5-5
```

- 기본 게이트웨이가 제공하는 Claude 모델은 `claude-opus-4-8`, `claude-opus-4-7`, `claude-sonnet-4`, `claude-haiku-4`다(2026-10-04 `GET /v1/models` 기준). 목록에 없는 모델을 지정하면 `HTTP 404 (Model not found.)`로 끝난다.
- 기본 모델을 `claude-sonnet-4`로 둔 이유는 `--temperature`가 실제로 적용되기 때문이다. `claude-opus-4-7`/`4-8`은 temperature를 지원하지 않는다([아래](#모델별-파라미터-제약) 참고). Anthropic 형식의 temperature 범위는 **0~1**이다.
- `max_tokens`는 생성 길이의 **상한**이고 실제 생성한 만큼만 과금된다. 값을 정한 근거는 [max_tokens 설정 기준](#max_tokens-설정-기준-실측)에 있다.
- 모델이 안전 정책으로 요청을 거절하면(HTTP 200 + `stop_reason: "refusal"`) 결과를 지어내지 않고 `[ERROR] 모델이 요청을 거절했습니다`로 종료(코드 2)한다. `claude-opus-5-5` 등 최신 모델에는 Anthropic 공식 API의 server-side fallback(`fallbacks: "default"`)을 함께 보내 거절 시 서버가 다른 모델로 한 번 더 시도하게 한다.

## 명령과 옵션

```bash
python3 main.py commit [옵션]   # 커밋 메시지 생성
python3 main.py pr     [옵션]   # PR 제목·본문 초안 생성
```

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--api-format` | `anthropic` | 요청 형식 `anthropic` / `openai` ([위](#요청-형식) 참고) |
| `--model` | `claude-sonnet-4` (openai: `gpt-5.5`) | 사용할 모델 |
| `--temperature` | `0.2` | 높을수록 표현이 다양해지고 낮을수록 일관적이다. 범위는 openai 형식 0~2, anthropic 형식 0~1이고 벗어나면 API를 호출하지 않고 종료(코드 1)한다. **모델이 지원할 때만 적용된다**(아래 참고) |
| `--max-tokens` | `16000` (openai: `2000`) | 응답 길이 상한. 결과가 이 값에 걸려 잘리면 `[WARN]`으로 알린다 |
| `--base-url` | `https://copa.codyssey.kr/v1` | API 주소 |
| `--timeout` | `30` | 요청 제한 시간(초) |
| `--staged` | 꺼짐 | 스테이징된 변경만 사용(`git diff --cached`). 스테이징한 것이 없으면 API를 호출하지 않고 종료한다 |
| `--no-safe-mode` | — | 마스킹·분량 제한 해제 (기본은 켜짐) |
| `--max-files` | `10` | safe-mode에서 보낼 최대 파일 수 |
| `--max-lines` | `200` | safe-mode에서 보낼 최대 diff 줄 수 |
| `--no-retry` | — | 형식 위반 시 재생성(2번째 호출)을 하지 않는다 |
| `--dry-run` | — | API를 호출하지 않고 보낼 프롬프트만 출력한다 (Key 불필요) |

숫자 옵션(`--max-tokens`, `--timeout`, `--max-files`, `--max-lines`)은 1 이상의 정수만 받는다. 잘못된 옵션 값은 사용 오류로 종료(코드 1)한다.

사용 예시:

```bash
python3 main.py commit                          # 기본값으로 커밋 메시지 생성
python3 main.py commit --staged                 # 스테이징한 변경만 요약
python3 main.py commit --temperature 0.7        # 표현을 더 다양하게
python3 main.py pr --max-tokens 3000            # 응답 길이 상한 조정
python3 main.py commit --model claude-haiku-4   # 다른 모델
python3 main.py commit --api-format openai      # OpenAI 호환 형식(gpt-5.5)
python3 main.py commit --dry-run                # 어떤 프롬프트가 나가는지 먼저 확인
```

### 모델별 파라미터 제약

GPT-5·o 계열(`gpt-5.5`, `gpt-5-mini`, `o3-mini` 등)은 **`temperature` 변경을 받지 않는다.** 기본값이 아닌 값을 보내면 공급자가 요청을 거부한다.
그래서 이 도구는 해당 모델에서는 `temperature`를 요청 본문에서 빼고 호출하며, 그 사실을 로그로 알린다.

```
[INFO] gpt-5.5 모델은 temperature 변경을 지원하지 않습니다. 지정한 0.2 대신 모델 기본값으로 호출합니다.
```

Claude 4.7 이후 세대(`claude-opus-4-7`, `claude-opus-4-8`, `claude-opus-5-5`, `claude-sonnet-5-5` 등)는 `temperature`를 **지원하지 않는다**. Anthropic 공식 API는 값을 보내면 400으로 거부하고, 기본 게이트웨이는 오류 없이 **무시**한다. 이 모델들에는 `temperature`를 빼고, 대신 `output_config.effort`를 `low`로 보내 짧은 요약 작업에 맞게 사고 깊이와 비용을 줄인다.

> 게이트웨이에서 확인한 방법(2026-10-04): 범위 밖 값 `temperature=5.0`을 보내면 `claude-sonnet-4`·`claude-haiku-4`는 `400 temperature: range: 0..1`로 거부하지만(값이 전달됨), `claude-opus-4-7`·`claude-opus-4-8`은 200으로 통과한다(값이 버려짐).

`--temperature`를 직접 지정했는데 그 모델이 지원하지 않으면 `[WARN]`으로 알린다. 이때 요청 로그에는 `temperature=모델 기본값`으로 표시된다. 그 밖의 Claude(`claude-sonnet-4`, `claude-haiku-4`)·Gemini·GPT-4 계열은 지정한 값이 그대로 적용된다.

### max_tokens 설정 기준 (실측)

`max_tokens`는 **목표 길이가 아니라 상한**이다. 실제 출력이 이 값보다 짧으면 아무 영향이 없고, 넘으면 문장 중간에서 잘린다. 과금은 실제 생성한 토큰만큼이다.
그래서 기준은 "정상 출력이 절대 잘리지 않을 만큼 넉넉하게, 단 폭주는 막을 만큼"이다.

이 저장소의 실제 커밋 10개와 작업 중 변경 1개, 총 11개 diff로 `commit`·`pr`을 각각 호출해(22회) 출력 토큰을 쟀다. (2026-10-04, `claude-sonnet-4`, temperature 0.2, 상한 16000, safe-mode 기본값)

| 명령 | 출력 토큰 최소 | 중앙값 | 평균 | 최대 | 1토큰당 글자 |
|---|---|---|---|---|---|
| `commit` | 109 | 211 | 208 | 268 | 약 1.4자 |
| `pr` | 380 | 879 | 805 | 1159 | 약 1.4자 |

- 22회 모두 `end_turn`(정상 종료)이었고 형식 규칙을 통과했다. 입력은 diff 크기에 따라 958~6912토큰이었다.
- PR은 커밋보다 약 4배 길다. 한국어는 1토큰이 1.4자 정도라 영어보다 토큰을 많이 쓴다.
- 상한을 너무 낮추면 잘린다. 실제로 `--max-tokens 60`은 커밋 첫 불릿 중간에서, `pr --max-tokens 120`은 `## Why` 섹션 중간에서 잘렸다.
- 기본값 16000은 관찰 최대(1159)의 10배 이상이라 잘릴 일이 없다. 넉넉하게 둔 이유는 `--model claude-opus-5-5`처럼 사고(thinking) 토큰까지 상한에 포함되는 모델을 지정해도 그대로 쓸 수 있게 하기 위해서다. 상한이 커도 비용은 늘지 않는다.
- openai 형식 기본값은 원래 700이었는데, 측정된 PR 11개 중 7개가 700을 넘었다(최대 1159). 그래서 관찰 최대의 약 1.7배인 **2000**으로 올렸다. 측정은 Claude 토크나이저 기준이다. GPT 토크나이저는 측정하지 못했다(키가 OpenAI 호환 엔드포인트에서 거부됨).
- 결과가 상한에 걸려 잘리면 형식 검증을 통과하더라도 `[WARN]`으로 알리고, 같은 상한으로는 또 잘리므로 재생성하지 않는다.

## 출력 예시

### 커밋 메시지 — openai 형식 (`python3 main.py commit --api-format openai`)

아래는 이 저장소에서 실제로 실행한 결과다. (게이트웨이 `copa.codyssey.kr`, 모델 `gpt-5.5`, openai 형식이 기본이던 시점의 실행이라 로그 형식이 지금과 조금 다르다)

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

### PR 초안 — openai 형식 (`python3 main.py pr --api-format openai`)

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

### 커밋 메시지 — anthropic 형식, 기본 (`python3 main.py commit --temperature 0.3`)

기본 모델을 `claude-sonnet-4`로 바꾼 변경 사항으로 실제 실행한 결과다. (게이트웨이 `copa.codyssey.kr`) 지정한 temperature가 그대로 전달된다.

```
[INFO] Git status 수집 완료: 4개 파일 변경 감지
[INFO] Git diff 수집 완료: 111줄 (민감정보 마스킹 적용)
[INFO] AI API 요청 중... (format=anthropic, model=claude-sonnet-4, temperature=0.3, max_tokens=16000)
[DONE] 커밋 메시지 생성 완료 (API 호출 1회)
------------------------------------------------------------
--- Commit Message ---
feat: anthropic 기본 모델을 claude-sonnet-4로 변경

- `config.py`의 `DEFAULT_MODELS["anthropic"]`을 `claude-opus-4-8`에서 `claude-sonnet-4`로 교체 — temperature가 실제로 적용되는 모델을 기본값으로 사용
- `tests/test_cli_e2e.py`에서 기본 모델 검증값 수정 및 `temperature` 전달 여부 테스트 추가, `claude-opus-4-8` 지정 시 `[WARN]` 출력 케이스 신규 추가
- `README.md`의 기본 모델 표기 및 모델별 파라미터 제약 설명을 실제 동작에 맞게 갱신
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

### 응답이 max_tokens 에 걸려 잘렸을 때

잘린 결과도 제목과 불릿이 있으면 형식 검증을 통과할 수 있으므로, 잘림 자체를 따로 확인해 경고한다. 같은 상한으로 다시 만들어도 또 잘리므로 재생성하지 않는다. (실제 실행 결과, `python3 main.py commit --max-tokens 60`)

```
[INFO] AI API 요청 중... (format=anthropic, model=claude-sonnet-4, temperature=0.2, max_tokens=60)
[WARN] 응답이 max_tokens(60)에 걸려 중간에 잘렸습니다. --max-tokens 를 늘려 다시 실행해 주세요.
[DONE] 커밋 메시지 생성 완료 (API 호출 1회)
------------------------------------------------------------
--- Commit Message ---
feat: anthropic 기본 모델을 claude-sonnet-4로 변경

- `config.py`의 `DEFAULT_MODELS["anthropic"]`을 `claude-opus-4-8`에서 `claude-sonnet
------------------------------------------------------------
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

응답이 `max_tokens`에 걸려 잘렸으면 경고하고 재생성은 건너뛴다.

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
| `1` | 환경·사용 오류 — API Key 없음, git 저장소 아님, git 미설치, 알 수 없는 `AI_API_FORMAT` 값, 범위를 벗어난 `--temperature`, 잘못된 명령·옵션 값 |
| `2` | API 오류 — 인증 실패(401/403), 요청 한도 초과(429), 없는 모델(404), 서버 오류(5xx), 시간 초과·연결 실패, 응답 형식 오류, 모델의 요청 거절 |

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
- [x] 변경 없음 → "변경 사항이 없습니다" 출력 후 종료 — `aicommit/cli.py:131`

**AI API 연동**

- [x] API Key는 환경변수로만 사용, 하드코딩 없음 — `aicommit/config.py:92`
- [x] 실행 시 API 호출 후 생성 결과를 터미널에 출력 — `aicommit/cli.py:183`
- [x] 호출 실패 시 원인을 포함한 메시지 (인증/한도/404/네트워크/응답 형식/거절) — `aicommit/client.py:109`
- [x] 모델·temperature·max_tokens를 CLI 옵션으로 변경 가능, 기본값 존재 — `aicommit/cli.py:74`
- [x] OpenAI 호환 · Anthropic Messages 두 요청 형식 지원 — `aicommit/client.py:73`

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
- [x] 검증 후 **재생성**과 **후처리**를 모두 적용 — `aicommit/cli.py:104`
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
python3 -m unittest discover -s tests -t .     # 124개 통과
python3 -m unittest tests.test_client          # 파일 하나만 (프로젝트 루트에서)
```

> `python tests/test_client.py`처럼 파일을 직접 실행하면 `ModuleNotFoundError: No module named 'aicommit'`가 난다. 파일 경로로 실행하면 파이썬이 `tests/` 폴더만 import 경로에 넣기 때문이다. 위처럼 프로젝트 루트에서 `-m` 모듈 방식으로 실행한다.

| 종류 | 검사 대상 |
|---|---|
| `test_sanitize.py` | 키·토큰·비밀번호·이메일·개인키 마스킹, camelCase·JSON 키·복수형 이름, 변수명 보존, 민감 단어를 포함만 한 이름(`author`, `max_tokens`) 미변경, 파일/줄 상한 |
| `test_gitctx.py` | **임시 git 저장소를 실제로 만들어** 변경 없음·수정·추적되지 않은 파일·스테이징(스테이징한 것만, 없으면 변경 없음)·커밋 없는 저장소·비(非)저장소 |
| `test_validate.py` | 제목/본문 파싱, 코드펜스 제거, 길이·섹션·불릿 검증, 후처리(단어 경계에서 자르기), 없는 섹션을 지어내지 않음 |
| `test_prompts.py` | 변경 파일·diff·브랜치·출력 규칙이 프롬프트에 포함되는지 |
| `test_client.py` | **로컬 스텁 HTTP 서버**로 요청 파라미터·헤더·경로, 응답 파싱, 401/429/500/잘못된 JSON/타임아웃/연결 실패, 호출 횟수, anthropic 형식(경로·`x-api-key`·system 분리·text 블록만 추출·temperature/effort·거절·max_tokens 소진), 잘림 감지(`stop_reason`/`finish_reason`) |
| `test_cli_e2e.py` | 실제 git 저장소 + 스텁 서버로 `main.py` 실행 — commit/pr 출력, 파라미터 전달, 재생성, safe-mode, dry-run, 변경 없음, `--staged` 빈 스테이징, Key 없음, 인증 실패, 저장소 아님, `.env` 읽기, 기본 형식(anthropic + `claude-sonnet-4`)·`--api-format openai`·`AI_API_FORMAT`, temperature 범위·숫자 옵션·잘못된 명령(종료 코드 1), 잘림 경고와 재생성 생략 |

테스트는 mock 라이브러리를 쓰지 않는다. git은 실제 임시 저장소로, API는 실제 HTTP 스텁 서버로 검증한다.

**실제 API 호출 검증** — 게이트웨이(`https://copa.codyssey.kr/v1`, 모델 `gpt-5.5`)로 `commit`과 `pr`을 각각 실행해 정상 동작을 확인했다. 위 [출력 예시](#출력-예시)가 그 결과다.

| 확인 항목 | 결과 |
|---|---|
| `GET /v1/models` | 사용 가능 모델 11종 확인 (gpt-5.5, gpt-5-mini, claude-*, gemini-* 등) |
| `commit` 실호출 | API 호출 1회, 제목 72자 이내, 불릿 4개 |
| `pr` 실호출 | API 호출 1회, 세 섹션 헤더와 섹션별 불릿 충족 |
| GPT-5 계열 `temperature` | 기본값이 아닌 값 전송 시 공급자 오류 → 요청 본문에서 제외하도록 처리 |
| anthropic 형식 `commit`·`pr` 실호출 (2026-10-04) | `POST /v1/messages`, 모델 `claude-opus-4-8`, 각각 API 호출 1회, 형식 규칙 충족 |
| anthropic 형식 기본 모델 `claude-sonnet-4` 실호출 | `temperature=0.3` 그대로 전달, API 호출 1회, 형식 규칙 충족 |
| Claude 모델별 `temperature` 적용 여부 | 범위 밖 값 5.0 전송 시 `sonnet-4`·`haiku-4`는 400(전달됨), `opus-4-7`·`opus-4-8`은 200(무시됨) |
| anthropic 형식 `claude-opus-5-5` | 게이트웨이에 없는 모델 → `HTTP 404 (Model not found.)` 오류로 안내 |
