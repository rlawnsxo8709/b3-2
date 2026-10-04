"""테스트용 스텁 AI API 서버 — mock 대신 실제 HTTP로 주고받는다."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class StubAPI:
    """응답을 미리 정해 두고, 받은 요청을 기록하는 작은 서버."""

    def __init__(self, responses=None, status=200, body=None, delay=0.0, api_format=None, disconnect=None):
        # responses: 호출 순서대로 돌려줄 본문 문자열 목록
        # api_format: 응답 모양 — openai(choices) / anthropic(content 블록). 없으면 요청 경로(/messages)로 고른다
        # disconnect: no_response(요청만 받고 응답 없이 끊음) / partial_body(본문을 다 보내기 전에 끊음)
        self.responses = list(responses or ["feat: 스텁 응답"])
        self.api_format = api_format
        self.status = status
        self.raw_body = body
        self.delay = delay
        self.disconnect = disconnect
        self.requests = []
        self._server = None
        self._thread = None

    @property
    def url(self):
        host, port = self._server.server_address
        return f"http://127.0.0.1:{port}/v1"

    def success_body(self, content, path=""):
        api_format = self.api_format or ("anthropic" if path.endswith("/messages") else "openai")
        if api_format == "anthropic":
            return {
                "type": "message", "role": "assistant", "model": "stub",
                "content": [{"type": "thinking", "thinking": "", "signature": "sig"},
                            {"type": "text", "text": content}],
                "stop_reason": "end_turn", "usage": {"input_tokens": 10, "output_tokens": 32},
            }
        return {"choices": [{"message": {"role": "assistant", "content": content}}], "usage": {"total_tokens": 42}}

    @property
    def call_count(self):
        return len(self.requests)

    def __enter__(self):
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                import time

                length = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(length) or b"{}")
                stub.requests.append({"path": self.path, "headers": dict(self.headers), "json": payload})
                if stub.delay:
                    time.sleep(stub.delay)
                if stub.disconnect == "no_response":
                    return  # 아무것도 쓰지 않고 돌아가면 서버가 연결을 닫는다

                if stub.raw_body is not None:
                    body = stub.raw_body.encode("utf8")
                elif stub.status != 200:
                    body = json.dumps({"error": {"message": "stub error", "code": "stub"}}).encode("utf8")
                else:
                    index = min(len(stub.requests) - 1, len(stub.responses) - 1)
                    content = stub.responses[index]
                    body = json.dumps(stub.success_body(content, self.path)).encode("utf8")
                # partial_body: 실제보다 긴 길이를 알려 두고 끊는다 — 클라이언트는 본문을 읽다가 끊긴다
                declared = len(body) * 2 if stub.disconnect == "partial_body" else len(body)

                try:
                    self.send_response(stub.status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(declared))
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    # 타임아웃 테스트에서 클라이언트가 먼저 끊는 경우 — 정상 상황이다
                    pass

            def log_message(self, *args):
                pass

            def handle_one_request(self):
                try:
                    super().handle_one_request()
                except (BrokenPipeError, ConnectionResetError):
                    self.close_connection = True

        self._server = HTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
        return False
