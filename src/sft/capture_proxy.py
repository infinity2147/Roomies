"""Logging reverse proxy for the OpenAI-compatible vLLM endpoint.

Records every /v1/chat/completions request body (messages + tools exactly as ADK/LiteLLM send
them) and the response, to a JSONL file. Used to (a) learn the exact request format for SFT
rendering and (b) round-trip-test src/sft/format.py.

Usage: .venv/bin/python -m src.sft.capture_proxy --listen 8012 --upstream http://127.0.0.1:8011 --out results/capture.jsonl
       then run evals with OPENAI_BASE_URL=http://127.0.0.1:8012/v1
"""

from __future__ import annotations

import argparse
import json
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOCK = threading.Lock()


def make_handler(upstream: str, out: str):
    class H(BaseHTTPRequestHandler):
        def _forward(self, method: str) -> None:
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n) if n else None
            req = urllib.request.Request(upstream + self.path, data=body, method=method,
                                         headers={k: v for k, v in self.headers.items() if k.lower() not in ("host", "content-length")})
            t0 = time.time()
            try:
                with urllib.request.urlopen(req, timeout=3600) as r:
                    data, status, headers = r.read(), r.status, r.headers
            except urllib.error.HTTPError as e:
                data, status, headers = e.read(), e.code, e.headers
            self.send_response(status)
            for k, v in headers.items():
                if k.lower() not in ("transfer-encoding", "connection", "content-length"):
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            if self.path.endswith("/chat/completions") and body:
                rec = {"t": t0, "dt": time.time() - t0, "status": status, "request": json.loads(body)}
                try:
                    rec["response"] = json.loads(data)
                except Exception:  # noqa: BLE001
                    rec["response_raw"] = data[:2000].decode("utf-8", "replace")
                with LOCK, open(out, "a") as f:
                    f.write(json.dumps(rec) + "\n")

        def do_POST(self):  # noqa: N802
            self._forward("POST")

        def do_GET(self):  # noqa: N802
            self._forward("GET")

        def log_message(self, *a):  # quiet
            pass

    return H


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", type=int, default=8012)
    ap.add_argument("--upstream", default="http://127.0.0.1:8011")
    ap.add_argument("--out", default="results/capture.jsonl")
    a = ap.parse_args()
    ThreadingHTTPServer(("127.0.0.1", a.listen), make_handler(a.upstream, a.out)).serve_forever()


if __name__ == "__main__":
    main()
