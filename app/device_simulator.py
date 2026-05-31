"""
Simple Anvil-style Device Simulator
REST API that simulates a hardware device for HIL testing.
No external dependencies — uses Python standard library only.
"""

import json
import time
import random
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

# ── Shared device state ───────────────────────────────────────────────────────
_lock  = threading.Lock()
_state = {
    "status":       "READY",
    "firmware":     os.getenv("FIRMWARE_VERSION", "fw-2.4.1-release"),
    "uptime":       0,
    "tests_run":    0,
    "tests_passed": 0,
    "tests_failed": 0,
}

def get_state():
    with _lock:
        return dict(_state)

def update_state(**kwargs):
    with _lock:
        _state.update(kwargs)


# ── RF sweep simulation ───────────────────────────────────────────────────────
def run_sweep(inject_fault=False):
    results = []
    for i in range(1, 4):
        time.sleep(0.1)
        if inject_fault and i == 2:
            delta = round(random.uniform(0.05, 0.12), 4)
        else:
            delta = round(random.uniform(0.001, 0.008), 4)
        results.append({
            "pass":   i,
            "delta":  delta,
            "result": "PASS" if delta < 0.010 else "FAIL"
        })
    return results


# ── HTTP handler ──────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {fmt % args}", flush=True)

    def send_json(self, code, body):
        data = json.dumps(body, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/")

        if path == "/health":
            self.send_json(200, {"status": "ok", "simulator": True})

        elif path == "/api/device/status":
            s = get_state()
            self.send_json(200, {
                "status":   s["status"],
                "firmware": s["firmware"],
                "uptime":   s["uptime"],
            })

        elif path == "/api/device/stats":
            s = get_state()
            self.send_json(200, {
                "tests_run":    s["tests_run"],
                "tests_passed": s["tests_passed"],
                "tests_failed": s["tests_failed"],
            })
        elif path == "":
            html = b"""<!DOCTYPE html>
        <html><head><title>Device Simulator</title></head>
        <body><h1>Anvil Device Simulator</h1></body></html>"""
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)

        else:
            self.send_json(404, {"error": "not found", "path": path})

    def do_POST(self):
        path   = urlparse(self.path).path.rstrip("/")
        length = int(self.headers.get("Content-Length", 0))
        body   = json.loads(self.rfile.read(length) or b"{}")

        if path == "/api/device/test":
            inject = body.get("inject_fault", False)
            update_state(status="TESTING")
            sweeps   = run_sweep(inject_fault=inject)
            all_pass = all(s["result"] == "PASS" for s in sweeps)

            with _lock:
                _state["tests_run"] += 1
                if all_pass:
                    _state["tests_passed"] += 1
                else:
                    _state["tests_failed"] += 1

            update_state(status="READY")
            self.send_json(200, {
                "result":   "PASS" if all_pass else "FAIL",
                "sweeps":   sweeps,
                "firmware": get_state()["firmware"],
            })

        elif path == "/api/device/reset":
            update_state(
                status="READY",
                tests_run=0,
                tests_passed=0,
                tests_failed=0
            )
            self.send_json(200, {"status": "RESET:ACK"})

        else:
            self.send_json(404, {"error": "not found", "path": path})


# ── Uptime counter ────────────────────────────────────────────────────────────
def uptime_counter():
    while True:
        time.sleep(1)
        with _lock:
            _state["uptime"] += 1


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", "8766"))
    print(f"Device simulator starting on port {port}", flush=True)
    print(f"Firmware: {get_state()['firmware']}", flush=True)

    threading.Thread(target=uptime_counter, daemon=True).start()

    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"Ready — http://0.0.0.0:{port}", flush=True)
    server.serve_forever()