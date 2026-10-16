"""Temporary hello-world fixture, not the mock payment service."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json


class HelloHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/hello":
            self.send_error(404)
            return
        body = json.dumps({"message": "hello from Daytona"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8000), HelloHandler).serve_forever()

