"""The HTTP front door holds the service key, so its auth is load-bearing."""
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from mcp import http_service as svc

SECRET = "test-secret"


@pytest.fixture
def server(monkeypatch):
    """A real server on an ephemeral port, with stub tools."""
    def echo(**kwargs):
        return {"got": kwargs}

    def explodes():
        raise RuntimeError("service key leaked in this message")

    monkeypatch.setattr(svc, "SECRET", SECRET)
    monkeypatch.setattr(svc, "TOOLS", {"echo": echo, "explodes": explodes})

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), svc.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def call(base, path, body=None, token=SECRET, raw=None):
    data = raw if raw is not None else json.dumps(body or {}).encode()
    req = urllib.request.Request(f"{base}{path}", data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if token is not None:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def test_health_needs_no_secret(server):
    with urllib.request.urlopen(f"{server}/health", timeout=10) as r:
        assert r.status == 200
        assert json.load(r)["ok"] is True


def test_tools_require_the_secret(server):
    assert call(server, "/tools/echo", token=None)[0] == 401


def test_a_wrong_secret_is_rejected(server):
    assert call(server, "/tools/echo", token="not-it")[0] == 401


def test_unknown_tool_is_404_only_once_authorised(server):
    # Unauthorised callers get 401 for a tool that does not exist either, so
    # the secret cannot be used to enumerate the tool list.
    assert call(server, "/tools/nope", token=None)[0] == 401
    assert call(server, "/tools/nope")[0] == 404


def test_arguments_reach_the_tool(server):
    status, body = call(server, "/tools/echo", {"start": "2026-01-01", "n": 3})
    assert status == 200
    assert body["result"]["got"] == {"start": "2026-01-01", "n": 3}


def test_empty_body_is_allowed(server):
    status, body = call(server, "/tools/echo", raw=b"")
    assert status == 200
    assert body["result"]["got"] == {}


def test_bad_json_is_400(server):
    assert call(server, "/tools/echo", raw=b"{not json")[0] == 400


def test_non_object_body_is_400(server):
    assert call(server, "/tools/echo", raw=b"[1,2,3]")[0] == 400


def test_unexpected_argument_is_400_not_500(server):
    status, body = call(server, "/tools/explodes", {"surprise": 1})
    assert status == 400
    assert "surprise" in body["error"]


def test_a_failing_tool_does_not_leak_its_message(server):
    status, body = call(server, "/tools/explodes")
    assert status == 500
    assert body["error"] == "explodes failed: RuntimeError"
    assert "service key" not in body["error"]


def test_oversized_body_is_refused(server):
    status, _ = call(server, "/tools/echo", raw=b"x" * (svc.MAX_BODY + 1))
    assert status == 413


def test_every_real_tool_is_reachable_by_name():
    """The route is the tool name, so the registry is the public surface."""
    from mcp.training_tools import TOOLS

    assert set(TOOLS) == {
        "training_summary",
        "training_week",
        "body_scan_log",
        "checkin_log",
    }
