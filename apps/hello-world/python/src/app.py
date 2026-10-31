"""Hello World service with RED metrics, JSON logs and failure modes.

Endpoints: /  /healthz  /metrics  /fail (500)  /slow?ms=N (adds latency)
Standard library only.
"""
import json
import os
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PORT = int(os.environ.get("PORT", "8080"))
SERVICE = os.environ.get("SERVICE_NAME", "python")
ROUTES = {"/", "/healthz", "/fail", "/slow"}
BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)

_lock = threading.Lock()
_requests = {}   # (method, route, status) -> count
_durations = {}  # (method, route) -> [bucket counts..., sum, count]


def log(level, msg, **fields):
    record = {"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
              "level": level, "msg": msg, "service": SERVICE, **fields}
    print(json.dumps(record), flush=True)


def observe(method, route, status, seconds):
    with _lock:
        key = (method, route, str(status))
        _requests[key] = _requests.get(key, 0) + 1
        h = _durations.setdefault((method, route), [0] * len(BUCKETS) + [0.0, 0])
        for i, bound in enumerate(BUCKETS):
            if seconds <= bound:
                h[i] += 1
        h[-2] += seconds
        h[-1] += 1


def exposition():
    lines = ["# HELP http_requests_total Requests handled, by route and status.",
             "# TYPE http_requests_total counter"]
    with _lock:
        for (m, r, s), v in sorted(_requests.items()):
            lines.append(f'http_requests_total{{method="{m}",route="{r}",status="{s}"}} {v}')
        lines += ["# HELP http_request_duration_seconds Request latency.",
                  "# TYPE http_request_duration_seconds histogram"]
        for (m, r), h in sorted(_durations.items()):
            for i, bound in enumerate(BUCKETS):
                lines.append(f'http_request_duration_seconds_bucket{{method="{m}",route="{r}",le="{bound}"}} {h[i]}')
            lines.append(f'http_request_duration_seconds_bucket{{method="{m}",route="{r}",le="+Inf"}} {h[-1]}')
            lines.append(f'http_request_duration_seconds_sum{{method="{m}",route="{r}"}} {h[-2]}')
            lines.append(f'http_request_duration_seconds_count{{method="{m}",route="{r}"}} {h[-1]}')
    return "\n".join(lines) + "\n"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # replaced by structured request logs
        pass

    def send(self, status, body, content_type="application/json"):
        payload = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/metrics":
            return self.send(200, exposition(), "text/plain; version=0.0.4")

        start = time.perf_counter()
        route = url.path if url.path in ROUTES else "other"
        if url.path == "/":
            status, body = 200, {"message": "Hello, World!", "language": "python"}
        elif url.path == "/healthz":
            status, body = 200, {"status": "ok"}
        elif url.path == "/fail":
            status, body = 500, {"error": "simulated failure"}
            log("error", "simulated failure", path=url.path, reason="requested via /fail")
        elif url.path == "/slow":
            ms = min(int(parse_qs(url.query).get("ms", ["1500"])[0] or 1500), 10000)
            time.sleep(ms / 1000)
            status, body = 200, {"message": "slow response", "delay_ms": ms}
        else:
            status, body = 404, {"error": "not found"}

        self.send(status, body)
        seconds = time.perf_counter() - start
        observe("GET", route, status, seconds)
        if route != "/healthz":
            level = "error" if status >= 500 else "warn" if seconds > 1 else "info"
            log(level, "request", method="GET", path=url.path, route=route,
                status=status, duration_ms=round(seconds * 1000, 1))


if __name__ == "__main__":
    log("info", "starting", port=PORT)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
