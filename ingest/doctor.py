"""Credential and connectivity check.

Answers "did I set this up right" precisely, instead of leaving you to read a
failed workflow log. Every check reports the exact remedy, and nothing here
changes any data.

    python -m ingest.run doctor
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx

TIMEOUT = httpx.Timeout(20.0, connect=10.0)


@dataclass
class Result:
    name: str
    ok: bool | None            # None means "not configured, and that is allowed"
    detail: str = ""
    remedy: str = ""


@dataclass
class Report:
    results: list[Result] = field(default_factory=list)

    def add(self, *r: Result) -> None:
        self.results.extend(r)

    @property
    def failures(self) -> list[Result]:
        return [r for r in self.results if r.ok is False]

    def render(self) -> str:
        lines = ["", "=== Setup check ===", ""]
        for r in self.results:
            mark = "PASS" if r.ok else "SKIP" if r.ok is None else "FAIL"
            lines.append(f"  {mark}  {r.name:<28} {r.detail}")
            if r.ok is False and r.remedy:
                lines.append(f"        -> {r.remedy}")
        lines.append("")
        if self.failures:
            lines.append(f"  {len(self.failures)} problem(s) to fix.")
        else:
            lines.append("  Everything configured is working.")
        lines.append("")
        return "\n".join(lines)


def _env(name: str) -> str | None:
    return os.environ.get(name) or None


# ---------------------------------------------------------------------------
# Supabase
# ---------------------------------------------------------------------------
def check_supabase() -> list[Result]:
    url, key, user = _env("SUPABASE_URL"), _env("SUPABASE_SERVICE_KEY"), _env("TI_USER_ID")

    missing = [n for n, v in
               (("SUPABASE_URL", url), ("SUPABASE_SERVICE_KEY", key), ("TI_USER_ID", user))
               if not v]
    if missing:
        return [Result("Supabase", False, f"missing {', '.join(missing)}",
                       "Set these first. Nothing else can work without them.")]

    base = url.rstrip("/")
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    out: list[Result] = []

    try:
        r = httpx.get(f"{base}/rest/v1/athlete_settings",
                      params={"select": "user_id,ftp_w,targets", "limit": "1"},
                      headers=headers, timeout=TIMEOUT)
    except httpx.HTTPError as e:
        return [Result("Supabase reachable", False, type(e).__name__,
                       f"Check SUPABASE_URL is right: {base}")]

    if r.status_code == 401:
        return [Result("Supabase key", False, "401 unauthorised",
                       "SUPABASE_SERVICE_KEY is wrong. Project Settings > API > service_role.")]
    if r.status_code == 404:
        return [Result("Migrations applied", False, "athlete_settings does not exist",
                       "Run supabase/migrations/0001_init.sql and 0002_rls.sql.")]
    if r.status_code >= 400:
        return [Result("Supabase", False, f"HTTP {r.status_code}", r.text[:120])]

    out.append(Result("Supabase reachable", True, base))

    rows = r.json()
    if not rows:
        out.append(Result("Seed applied", False, "athlete_settings is empty",
                          "Run supabase/seed/athlete_settings.sql, after creating the auth user."))
        return out

    row = rows[0]
    out.append(Result("Seed applied", True,
                      f"ftp {row.get('ftp_w')}, protein {(row.get('targets') or {}).get('protein_g')}"))

    if row.get("user_id") != user:
        out.append(Result("TI_USER_ID matches", False,
                          f"settings row belongs to {row.get('user_id')}",
                          "TI_USER_ID does not match the seeded row. Use the id the seed printed."))
    else:
        out.append(Result("TI_USER_ID matches", True, user))

    # Storage bucket for Evolt uploads.
    rb = httpx.get(f"{base}/storage/v1/bucket/evolt-scans", headers=headers, timeout=TIMEOUT)
    if rb.status_code == 200:
        public = rb.json().get("public")
        out.append(Result("evolt-scans bucket", not public,
                          "private" if not public else "PUBLIC",
                          "The bucket is public. It holds body scans. Make it private."))
    else:
        out.append(Result("evolt-scans bucket", False, f"HTTP {rb.status_code}",
                          "Run 0002_rls.sql, which creates the bucket."))

    return out


# ---------------------------------------------------------------------------
# Strava
# ---------------------------------------------------------------------------
def check_strava() -> list[Result]:
    cid, secret, refresh = (_env("STRAVA_CLIENT_ID"), _env("STRAVA_CLIENT_SECRET"),
                            _env("STRAVA_REFRESH_TOKEN"))
    if not any((cid, secret, refresh)):
        return [Result("Strava", None, "not configured")]

    missing = [n for n, v in (("STRAVA_CLIENT_ID", cid), ("STRAVA_CLIENT_SECRET", secret),
                              ("STRAVA_REFRESH_TOKEN", refresh)) if not v]
    if missing:
        return [Result("Strava", False, f"missing {', '.join(missing)}",
                       "Run scripts/strava_token.py to get all three.")]

    try:
        r = httpx.post("https://www.strava.com/oauth/token", timeout=TIMEOUT, data={
            "client_id": cid, "client_secret": secret,
            "grant_type": "refresh_token", "refresh_token": refresh,
        })
    except httpx.HTTPError as e:
        return [Result("Strava reachable", False, type(e).__name__)]

    if r.status_code >= 400:
        return [Result("Strava token", False, f"HTTP {r.status_code}",
                       "Credentials rejected. Re-run scripts/strava_token.py.")]

    token = r.json()["access_token"]
    out = [Result("Strava token", True, "refreshed")]

    # Scope check: the ingest needs activities and the athlete's gear.
    ra = httpx.get("https://www.strava.com/api/v3/athlete",
                   headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT)
    if ra.status_code == 200:
        body = ra.json()
        shoes = len(body.get("shoes") or [])
        out.append(Result("Strava profile scope", True, f"{shoes} shoe(s) visible"))
    else:
        out.append(Result("Strava profile scope", False, f"HTTP {ra.status_code}",
                          "Missing profile:read_all. Re-authorise with both scopes."))

    rl = httpx.get("https://www.strava.com/api/v3/athlete/activities",
                   params={"per_page": 1},
                   headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT)
    if rl.status_code == 200:
        out.append(Result("Strava activity scope", True, f"{len(rl.json())} activity visible"))
    else:
        out.append(Result("Strava activity scope", False, f"HTTP {rl.status_code}",
                          "Missing activity:read_all. Re-authorise with both scopes."))
    return out


# ---------------------------------------------------------------------------
# Garmin
# ---------------------------------------------------------------------------
def check_garmin() -> list[Result]:
    """The login route is the primary source; the Personal API is optional.

    Without one of them there is no sleep, HRV or resting HR, so readiness
    cannot be computed at all. That is a failure, not a skip.
    """
    out: list[Result] = []
    email, password = _env("GARMIN_EMAIL"), _env("GARMIN_PASSWORD")
    token = _env("GARMIN_PERSONAL_TOKEN")

    if email and password:
        try:
            import garminconnect  # noqa: F401
            out.append(Result("Garmin login route", True,
                              "credentials set, library present"))
        except ImportError:
            out.append(Result("Garmin login route", False,
                              "garminconnect is not installed",
                              "pip install -r requirements.txt"))
    elif token:
        out.append(Result("Garmin login route", None,
                          "not configured, using the official API instead"))
    else:
        out.append(Result("Garmin", False, "no Garmin source configured",
                          "Set GARMIN_EMAIL and GARMIN_PASSWORD. Without a Garmin "
                          "source there is no sleep, HRV or resting HR, so readiness "
                          "cannot be computed."))

    if not token:
        out.append(Result("Garmin Personal API", None,
                          "not configured, which is fine: the login route covers "
                          "strictly more"))
        return out

    from datetime import datetime, timedelta, timezone

    from .garmin_personal import BASE, ENDPOINTS

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=1)
    try:
        r = httpx.get(
            f"{BASE}{ENDPOINTS['daily']}",
            headers={"Authorization": f"Bearer {token}"},
            params={"uploadStartTimeInSeconds": int(start.timestamp()),
                    "uploadEndTimeInSeconds": int(end.timestamp())},
            timeout=TIMEOUT,
        )
    except httpx.HTTPError as e:
        out.append(Result("Garmin Personal API", False, type(e).__name__))
        return out

    if r.status_code == 401:
        out.append(Result("Garmin Personal API", False, "401 unauthorised",
                          "Token rejected. Regenerate at developer.garmin.com, or "
                          "drop it and rely on the login route."))
    elif r.status_code == 404:
        out.append(Result("Garmin Personal API", False, "404 on the dailies endpoint",
                          "Endpoint path is wrong. Check the swagger against the "
                          "ENDPOINTS block in ingest/garmin_personal.py."))
    elif r.status_code >= 400:
        out.append(Result("Garmin Personal API", False, f"HTTP {r.status_code}"))
    else:
        out.append(Result("Garmin Personal API", True,
                          f"{len(r.json() or [])} summary in the last 24h"))
    return out


def check_freshness() -> list[Result]:
    """What each source last did, read from sync_status.

    This is the check that answers "is it actually running", as opposed to
    "are the credentials shaped right".
    """
    url, key, user = _env("SUPABASE_URL"), _env("SUPABASE_SERVICE_KEY"), _env("TI_USER_ID")
    if not (url and key and user):
        return []

    try:
        r = httpx.get(
            f"{url.rstrip('/')}/rest/v1/sync_status",
            params={"select": "source,last_success,last_error", "user_id": f"eq.{user}"},
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            timeout=TIMEOUT,
        )
    except httpx.HTTPError:
        return []
    if r.status_code >= 400:
        return []

    rows = r.json()
    if not rows:
        return [Result("Last run", None, "nothing has ingested yet")]

    out: list[Result] = []
    for row in sorted(rows, key=lambda x: x["source"]):
        err = row.get("last_error")
        when = (row.get("last_success") or "never")[:16].replace("T", " ")
        out.append(Result(
            f"Last run: {row['source']}",
            not err,
            f"ok {when}" if not err else f"last error: {err[:70]}",
            "Open the failing step in the Actions log." if err else "",
        ))
    return out


# ---------------------------------------------------------------------------
# Optional extras
# ---------------------------------------------------------------------------
def check_extras() -> list[Result]:
    out: list[Result] = []

    topic = _env("NTFY_TOPIC")
    out.append(Result("ntfy topic", True if topic else None,
                      "set" if topic else "not configured, no Sunday push"))

    if os.environ.get("NTFY_INCLUDE_SENSITIVE") == "1":
        out.append(Result("ntfy sensitivity", False, "NTFY_INCLUDE_SENSITIVE=1",
                          "This sends health detail to a public relay. Set it to 0."))
    else:
        out.append(Result("ntfy sensitivity", True, "health detail stays off the relay"))

    out.append(Result("Evolt vision fallback",
                      True if _env("ANTHROPIC_API_KEY") else None,
                      "available" if _env("ANTHROPIC_API_KEY")
                      else "not configured, text-layer parsing only"))
    return out


def run() -> Report:
    report = Report()
    report.add(*check_supabase())
    report.add(*check_strava())
    report.add(*check_garmin())
    report.add(*check_extras())
    report.add(*check_freshness())
    return report
