"""A stand-in for the Studio's API (and the presigned upload URL), for the scaling script tests.

Routes come from a JSON file keyed by "<METHOD> <path>": either one response, {"status": 200,
"headers": {...}, "body": ...}, or a list of them answered in turn, the last one repeated. A body
that is not a string is sent as JSON; "{base}" in a body becomes this server's URL. Unknown routes
answer 404. Every request is appended to <routes file>.log as one line,
"<METHOD> <path> cookie=<Cookie header> body=<body>", with newlines written as \\n; a PUT body
(an uploaded file) is logged as "sha256=<hex>". Prints the port it listens on.
Usage: python3 -I fake_api.py <routes file>
"""

import hashlib
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROUTES_FILE = sys.argv[1]
answered: dict[str, int] = {}
lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def _answer(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        sent = self.rfile.read(length) if length else b""
        key = f"{self.command} {self.path}"
        if self.command == "PUT":
            logged = f"sha256={hashlib.sha256(sent).hexdigest()}"
        else:
            logged = sent.decode().replace("\n", "\\n")
        with lock:
            with open(ROUTES_FILE, encoding="utf-8") as f:
                routes = json.load(f)
            with open(ROUTES_FILE + ".log", "a", encoding="utf-8") as log:
                log.write(f"{key} cookie={self.headers.get('Cookie', '')} body={logged}\n")
            route = routes.get(key, {"status": 404, "body": {"detail": "Not Found"}})
            if isinstance(route, list):
                turn = answered.get(key, 0)
                answered[key] = turn + 1
                route = route[min(turn, len(route) - 1)]
        body = route.get("body", "")
        text = body if isinstance(body, str) else json.dumps(body)
        data = text.replace("{base}", f"http://127.0.0.1:{self.server.server_address[1]}").encode()
        self.send_response(route["status"])
        for name, value in route.get("headers", {}).items():
            self.send_header(name, value)
        if not isinstance(body, str):
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = do_POST = do_PUT = do_DELETE = _answer  # noqa: N815 (http.server's names)

    def log_message(self, *args: object) -> None:
        pass


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
print(server.server_address[1], flush=True)
server.serve_forever()
