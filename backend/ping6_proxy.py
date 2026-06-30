# -*- coding: utf-8 -*-
# IPv6 Ping Proxy - runs on Windows host for Docker containers
# Start: python ping6_proxy.py
import subprocess
import platform
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

IS_WIN = platform.system() == "Windows"


def ping6(ip, timeout=3):
    if IS_WIN:
        cmd = ["ping", "-6", "-n", "1", "-w", str(timeout * 1000), ip]
    else:
        cmd = ["ping", "-6", "-c", "1", "-W", str(timeout), ip]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5)
        return result.returncode == 0
    except Exception:
        return False


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/ping6":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        ips = body.get("ips", [])
        results = {}
        for ip in ips:
            results[ip] = ping6(ip)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(results).encode())

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
            return
        self.send_error(404)

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 5199), Handler)
    print("IPv6 Ping Proxy started on port 5199")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopped")
