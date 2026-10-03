"""CLI가 사용자에게 그대로 보여줄 수 있는 오류들.

exit_code 를 예외가 들고 다니므로, cli.py 는 예외 하나만 잡아 종료 코드를 정한다.
  1 = 환경·사용 오류(키 없음, git 저장소 아님)   2 = API 오류(인증·한도·네트워크·응답 형식)
"""


class AICommitError(Exception):
    """사용자에게 보여줄 메시지를 가진 오류."""

    exit_code = 1


class NotAGitRepository(AICommitError):
    """현재 디렉토리가 git 저장소가 아니다."""


class GitCommandError(AICommitError):
    """git 명령 실행이 실패했다."""


class MissingAPIKey(AICommitError):
    """API Key 환경변수가 없다."""


class APIError(AICommitError):
    """AI API 호출이 실패했다."""

    exit_code = 2


class AuthError(APIError):
    """인증 실패(401/403)."""


class RateLimitError(APIError):
    """요청 한도 초과(429)."""


class NetworkError(APIError):
    """연결 실패 또는 시간 초과."""


class ResponseFormatError(APIError):
    """응답이 예상한 JSON 구조가 아니다."""
