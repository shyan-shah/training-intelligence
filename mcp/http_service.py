"""HTTP front door for the four training tools.

`vault-mcp` is TypeScript, so it cannot import `training_tools` directly. It
calls this instead, and the analytics stay in one language: `hrv_state`,
`gain_quality` and `validate_scan` are the tested engine, and a second
implementation of them in TypeScript would be free to drift. The write tools
matter most here — validation that disagrees with the app would let rows in
that the app would have rejected.

Stdlib only, like the rest of the engine. One user, four endpoints, no
framework earns its place.

    POST /tools/<name>   JSON body is the tool's keyword arguments
    GET  /health         liveness, no secret required

Every /tools call needs `Authorization: Bearer $TRAINING_API_SECRET`. This
server holds the Supabase service key, so an unauthenticated caller would own
the data; the secret is the only thing in front of it.
"""
from __future__ import annotations

import hmac
import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from mcp.training_tools import TOOLS

log = logging.getLogger(__name__)

SECRET = os.environ.get("TRAINING_API_SECRET", "")
MAX_BODY = 64 * 1024


class Handler(BaseHTTPRequestHandler):
    server_version = "training-intelligence/1.0"

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorised(self) -> bool:
        # compare_digest, not ==: a plain comparison leaks the secret one
        # character at a time to anyone who can time the response.
        header = self.headers.get("Authorization", "")
        token = header[7:] if header.startswith("Bearer ") else ""
        return bool(SECRET) and hmac.compare_digest(token, SECRET)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") in ("", "/health"):
            self._send(200, {"ok": True, "tools": sorted(TOOLS)})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if not self.path.startswith("/tools/"):
            self._send(404, {"error": "not found"})
            return

        if not self._authorised():
            # No detail: a caller without the secret learns nothing about
            # whether the tool exists.
            self._send(401, {"error": "unauthorized"})
            return

        name = self.path[len("/tools/"):].strip("/")
        fn = TOOLS.get(name)
        if fn is None:
            self._send(404, {"error": f"unknown tool: {name}"})
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._send(400, {"error": "bad Content-Length"})
            return
        if length > MAX_BODY:
            self._send(413, {"error": "body too large"})
            return

        try:
            raw = self.rfile.read(length) if length else b"{}"
            args = json.loads(raw or b"{}")
        except (ValueError, OSError) as e:
            self._send(400, {"error": f"bad JSON: {e}"})
            return

        if not isinstance(args, dict):
            self._send(400, {"error": "body must be a JSON object"})
            return

        try:
            self._send(200, {"result": fn(**args)})
        except TypeError as e:
            # Wrong or unexpected argument names: the caller's fault, not ours.
            self._send(400, {"error": str(e)})
        except Exception as e:  # noqa: BLE001
            # The message reaches a model, so say what failed without putting
            # the service key or a raw payload into a chat.
            log.exception("%s failed", name)
            self._send(500, {"error": f"{name} failed: {type(e).__name__}"})

    def log_message(self, fmt: str, *args) -> None:
        # Default handler writes the full path to stderr. Keep the shape.
        log.info("%s %s", self.address_string(), fmt % args)


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    if not SECRET:
        raise SystemExit(
            "TRAINING_API_SECRET is not set. This server holds the Supabase "
            "service key; refusing to start without the shared secret."
        )
    port = int(os.environ.get("PORT", "8000"))
    log.info("training tools on :%d — %s", port, ", ".join(sorted(TOOLS)))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
