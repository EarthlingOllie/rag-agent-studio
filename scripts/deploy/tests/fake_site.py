"""A stand-in for the deployed CloudFront URL, for the deploy script tests.

Serves fixed responses from a JSON file: {"<path>": {"status": 200, "headers": {...}, "body": "..."}}.
Unknown paths answer 404. Every request path is appended to <routes file>.log. Prints the port it listens on.
Usage: python3 -I fake_site.py <routes file>
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROUTES_FILE = sys.argv[1]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (http.server's name)
        with open(ROUTES_FILE, encoding="utf-8") as f:
            routes = json.load(f)
        with open(ROUTES_FILE + ".log", "a", encoding="utf-8") as log:
            log.write(self.path + "\n")
        route = routes.get(self.path, {"status": 404, "headers": {}, "body": "not found"})
        body = route.get("body", "").encode()
        self.send_response(route["status"])
        for name, value in route.get("headers", {}).items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        pass


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
print(server.server_address[1], flush=True)
server.serve_forever()
