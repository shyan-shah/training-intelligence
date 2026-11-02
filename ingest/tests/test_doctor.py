"""Tests for the setup doctor.

The doctor's only job is to say precisely what is wrong, so these assert the
diagnosis and the remedy, not just that it failed. A check that reports
"Supabase: error" is no better than reading the workflow log.

A local HTTP server stands in for PostgREST, so no network and no real
project are involved.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from ingest import doctor

OWNER = "11111111-1111-1111-1111-111111111111"
OTHER = "99999999-9999-9999-9999-999999999999"
GOOD_KEY = "service-key"


def make_handler(mode: str):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body):
            payload = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            if mode == "bad_key" or self.headers.get("apikey") != GOOD_KEY:
                return self._send(401, {"message": "Invalid API key"})

            if self.path.startswith("/rest/v1/athlete_settings"):
                if mode == "no_tables":
                    return self._send(404, {"message": "relation does not exist"})
                if mode == "no_seed":
                    return self._send(200, [])
                owner = OTHER if mode == "wrong_user" else OWNER
                return self._send(200, [{
                    "user_id": owner, "ftp_w": 213, "targets": {"protein_g": 216},
                }])

            if self.path.startswith("/storage/v1/bucket/evolt-scans"):
                if mode == "public_bucket":
                    return self._send(200, {"id": "evolt-scans", "public": True})
                if mode == "no_bucket":
                    return self._send(404, {"message": "not found"})
                return self._send(200, {"id": "evolt-scans", "public": False})

            return self._send(404, {"message": "no route"})

    return Handler


@pytest.fixture
def fake_supabase():
    servers = []

    def start(mode: str) -> str:
        server = HTTPServer(("127.0.0.1", 0), make_handler(mode))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return f"http://127.0.0.1:{server.server_port}"

    yield start
    for s in servers:
        s.shutdown()


def configure(monkeypatch, url: str, key: str = GOOD_KEY, user: str = OWNER):
    monkeypatch.setenv("SUPABASE_URL", url)
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", key)
    monkeypatch.setenv("TI_USER_ID", user)
    # Keep the optional sources out of the way.
    for name in ("STRAVA_CLIENT_ID", "STRAVA_CLIENT_SECRET", "STRAVA_REFRESH_TOKEN",
                 "GARMIN_PERSONAL_TOKEN", "GARMIN_EMAIL", "GARMIN_PASSWORD",
                 "NTFY_TOPIC", "ANTHROPIC_API_KEY", "NTFY_INCLUDE_SENSITIVE"):
        monkeypatch.delenv(name, raising=False)


def find(results, name):
    return next((r for r in results if r.name == name), None)


# ---------------------------------------------------------------------------
# Supabase diagnoses
# ---------------------------------------------------------------------------
def test_missing_variables_are_named_individually(monkeypatch):
    for name in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "TI_USER_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SUPABASE_URL", "http://example.invalid")

    r = doctor.check_supabase()[0]
    assert r.ok is False
    assert "SUPABASE_SERVICE_KEY" in r.detail
    assert "TI_USER_ID" in r.detail
    assert "SUPABASE_URL" not in r.detail      # that one was set


def test_bad_key_is_diagnosed_as_the_key(monkeypatch, fake_supabase):
    configure(monkeypatch, fake_supabase("bad_key"), key="wrong")
    r = doctor.check_supabase()[0]
    assert r.ok is False
    assert "401" in r.detail
    assert "service_role" in r.remedy


def test_missing_tables_points_at_the_migrations(monkeypatch, fake_supabase):
    configure(monkeypatch, fake_supabase("no_tables"))
    r = doctor.check_supabase()[0]
    assert r.ok is False
    assert r.name == "Migrations applied"
    assert "0001_init.sql" in r.remedy


def test_empty_table_points_at_the_seed(monkeypatch, fake_supabase):
    configure(monkeypatch, fake_supabase("no_seed"))
    results = doctor.check_supabase()
    assert find(results, "Supabase reachable").ok is True
    seed = find(results, "Seed applied")
    assert seed.ok is False
    assert "athlete_settings.sql" in seed.remedy


def test_mismatched_user_id_is_caught(monkeypatch, fake_supabase):
    """The row exists but belongs to someone else, which means TI_USER_ID was
    copied from the wrong place. Silently ingesting into a different user is
    the worst outcome here."""
    configure(monkeypatch, fake_supabase("wrong_user"))
    r = find(doctor.check_supabase(), "TI_USER_ID matches")
    assert r.ok is False
    assert OTHER in r.detail


def test_public_scan_bucket_is_a_failure(monkeypatch, fake_supabase):
    """The bucket holds body scans. Public is not a warning."""
    configure(monkeypatch, fake_supabase("public_bucket"))
    r = find(doctor.check_supabase(), "evolt-scans bucket")
    assert r.ok is False
    assert "PUBLIC" in r.detail


def test_missing_bucket_points_at_the_rls_migration(monkeypatch, fake_supabase):
    configure(monkeypatch, fake_supabase("no_bucket"))
    r = find(doctor.check_supabase(), "evolt-scans bucket")
    assert r.ok is False
    assert "0002_rls.sql" in r.remedy


def test_a_correct_setup_passes_everything(monkeypatch, fake_supabase):
    configure(monkeypatch, fake_supabase("ok"))
    results = doctor.check_supabase()
    assert [r.name for r in results if r.ok is not True] == []
    assert find(results, "Seed applied").detail == "ftp 213, protein 216"


def test_unreachable_host_is_not_reported_as_a_key_problem(monkeypatch):
    configure(monkeypatch, "http://127.0.0.1:1")     # nothing listening
    r = doctor.check_supabase()[0]
    assert r.ok is False
    assert r.name == "Supabase reachable"


# ---------------------------------------------------------------------------
# Optional sources
# ---------------------------------------------------------------------------
def test_unconfigured_strava_skips_rather_than_fails(monkeypatch):
    for name in ("STRAVA_CLIENT_ID", "STRAVA_CLIENT_SECRET", "STRAVA_REFRESH_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    assert doctor.check_strava()[0].ok is None


def test_no_garmin_source_at_all_is_a_failure(monkeypatch):
    """Without Garmin there is no sleep, HRV or resting HR, so readiness
    cannot be computed. That is not a skip."""
    for name in ("GARMIN_EMAIL", "GARMIN_PASSWORD", "GARMIN_PERSONAL_TOKEN"):
        monkeypatch.delenv(name, raising=False)

    r = find(doctor.check_garmin(), "Garmin")
    assert r.ok is False
    assert "GARMIN_EMAIL" in r.remedy
    assert "readiness" in r.remedy


def test_login_route_alone_is_a_complete_setup(monkeypatch):
    """The Personal key is optional: the login route covers strictly more."""
    monkeypatch.setenv("GARMIN_EMAIL", "a@b.c")
    monkeypatch.setenv("GARMIN_PASSWORD", "secret")
    monkeypatch.delenv("GARMIN_PERSONAL_TOKEN", raising=False)

    results = doctor.check_garmin()
    assert find(results, "Garmin login route").ok is True
    personal = find(results, "Garmin Personal API")
    assert personal.ok is None
    assert "strictly more" in personal.detail
    assert not [r for r in results if r.ok is False]


def test_partial_strava_credentials_fail_and_name_the_helper(monkeypatch):
    monkeypatch.setenv("STRAVA_CLIENT_ID", "123")
    monkeypatch.delenv("STRAVA_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("STRAVA_REFRESH_TOKEN", raising=False)

    r = doctor.check_strava()[0]
    assert r.ok is False
    assert "STRAVA_CLIENT_SECRET" in r.detail
    assert "strava_token.py" in r.remedy


def test_sensitive_ntfy_is_a_failure(monkeypatch):
    """Health detail on a public relay is the thing the flag exists to stop."""
    monkeypatch.setenv("NTFY_INCLUDE_SENSITIVE", "1")
    r = find(doctor.check_extras(), "ntfy sensitivity")
    assert r.ok is False
    assert "public relay" in r.remedy


def test_default_ntfy_keeps_health_detail_off_the_relay(monkeypatch):
    monkeypatch.delenv("NTFY_INCLUDE_SENSITIVE", raising=False)
    assert find(doctor.check_extras(), "ntfy sensitivity").ok is True


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def test_report_renders_remedies_only_for_failures(monkeypatch, fake_supabase):
    configure(monkeypatch, fake_supabase("no_seed"))
    report = doctor.Report()
    report.add(*doctor.check_supabase())
    text = report.render()

    assert "FAIL" in text and "PASS" in text
    assert "athlete_settings.sql" in text
    assert "problem(s) to fix" in text


def test_clean_report_says_so(monkeypatch, fake_supabase):
    configure(monkeypatch, fake_supabase("ok"))
    report = doctor.Report()
    report.add(*doctor.check_supabase())
    assert report.failures == []
    assert "Everything configured is working" in report.render()
