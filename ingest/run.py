"""Ingest CLI. One entry point per source, so a failing source fails only its
own workflow step.

    python -m ingest.run garmin-personal --days 7
    python -m ingest.run garmin-login   --days 7
    python -m ingest.run strava         --days 90
    python -m ingest.run evolt
    python -m ingest.run audit
    python -m ingest.run doctor
"""
from __future__ import annotations

import argparse
import logging
import sys
import tempfile
from pathlib import Path

from engine.ti.config import Config, ConfigError
from engine.ti.db import Db

from . import evolt as evolt_mod
from . import garmin_login, garmin_personal, strava

log = logging.getLogger("ingest")


def cmd_garmin_personal(cfg: Config, db: Db, args) -> None:
    """The official Health API. Optional: only runs if a key is configured.

    Covers strictly less than the login route (no readiness, training status
    or VO2max) and its endpoint paths are unverified, so it is the
    alternative rather than the default.
    """
    if not cfg.garmin_personal_token:
        log.info("GARMIN_PERSONAL_TOKEN not set, skipping the official API")
        return
    counts = garmin_personal.ingest(cfg, db, days=args.days)
    log.info("garmin personal api: %s", counts)


def cmd_garmin_login(cfg: Config, db: Db, args) -> None:
    """The primary Garmin source: wellness, body composition and activities.

    Raises on failure. With the login route as the only Garmin source, a
    swallowed error would leave the page quietly empty, which is worse than a
    red workflow run.
    """
    counts = garmin_login.ingest(cfg, db, days=args.days, strict=True)
    log.info("garmin login route: %s", counts)


def cmd_strava(cfg: Config, db: Db, args) -> None:
    """Optional. Garmin already covers activities and gear.

    Worth adding only if something reaches Strava without going through the
    watch first, a Zwift ride synced directly for example. Deduping handles
    the overlap when both are on.
    """
    if not (cfg.strava_client_id and cfg.strava_client_secret and cfg.strava_refresh_token):
        log.info("Strava not configured, skipping. Garmin covers activities and gear.")
        return
    n = strava.ingest_activities(cfg, db, days=args.days)
    g = strava.ingest_gear(cfg, db)
    log.info("strava: %d activities, %d gear items", n, g)


def cmd_evolt(cfg: Config, db: Db, args) -> None:
    """Parse any scan that was uploaded through the app but not yet read.

    The upload route stores the PDF and writes a placeholder row; parsing
    happens here so pdfplumber and the range checks exist in one language only.
    """
    pending = db.select("evolt_scans", columns="id,pdf_path,scanned_at,conditions",
                        parse_method="eq.pending")
    if not pending:
        log.info("evolt: nothing pending")
        return

    import httpx

    for row in pending:
        path = row.get("pdf_path")
        if not path:
            continue

        url = f"{cfg.supabase_url}/storage/v1/object/evolt-scans/{path}"
        r = httpx.get(url, timeout=60.0, headers={
            "apikey": cfg.supabase_service_key,
            "Authorization": f"Bearer {cfg.supabase_service_key}",
        })
        if r.status_code >= 400:
            log.warning("evolt: could not fetch %s (HTTP %s)", path, r.status_code)
            db.update("evolt_scans",
                      {"parse_method": "manual", "needs_review": True,
                       "review_reason": f"could not fetch the stored PDF (HTTP {r.status_code})"},
                      id=f"eq.{row['id']}")
            continue

        # Write to a dedicated temp directory, and pass the path as an
        # argument: never run an interpreter from inside it.
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "scan.pdf"
            local.write_bytes(r.content)
            scan = evolt_mod.parse_pdf(local, allow_vision_fallback=True,
                                       api_key=cfg.anthropic_api_key)

        values = evolt_mod.to_row(scan, pdf_path=path, conditions=row.get("conditions") or {})
        # Keep the upload timestamp if the PDF carried no date of its own.
        if scan.scanned_at is None:
            values["scanned_at"] = row["scanned_at"]
        db.update("evolt_scans", values, id=f"eq.{row['id']}")
        log.info("evolt: parsed %s (review=%s)", path, scan.needs_review)

    db.mark_sync("evolt", ok=True)


def cmd_audit(cfg: Config, db: Db, args) -> None:
    """Report the state of every source without changing anything.

    This is the 'audit first' acceptance check: run it before any migration or
    backfill and read the output.
    """
    print("\n=== Ingest audit ===\n")

    for table, order in (("garmin_daily", "day"), ("activities", "start_at"),
                         ("evolt_scans", "scanned_at"), ("daily_checkin", "day"),
                         ("nutrition_daily", "day"), ("daily_load", "day"),
                         ("daily_readiness", "day"), ("daily_scorecard", "day")):
        try:
            newest = db.select(table, columns=order, order=f"{order}.desc", limit=1)
            total = db.select(table, columns=order, limit=10000)
            last = newest[0][order][:10] if newest else "never"
            print(f"  {table:<18} rows={len(total):<6} latest={last}")
        except Exception as e:
            print(f"  {table:<18} ERROR: {e}")

    print("\n  Sync status")
    for s in db.select("sync_status"):
        print(f"    {s['source']:<18} ok={s.get('last_success')} "
              f"err={s.get('last_error') or '-'} token_exp={s.get('token_expires_at') or '-'}")

    try:
        settings = db.settings()
        print("\n  Settings")
        for key in ("ftp_w", "threshold_pace", "css_swim", "lthr", "max_hr"):
            value = settings.get(key)
            print(f"    {key:<16} {value if value is not None else 'NOT SET'}")
    except Exception as e:
        print(f"\n  Settings ERROR: {e}")

    print()


def cmd_doctor() -> int:
    """Check every credential and say exactly what is wrong.

    Runs before Config is built, because the whole point is diagnosing the
    case where the config is incomplete.
    """
    from . import doctor as doctor_mod

    report = doctor_mod.run()
    print(report.render())
    return 1 if report.failures else 0


COMMANDS = {
    "garmin-personal": cmd_garmin_personal,
    "garmin-login": cmd_garmin_login,
    "strava": cmd_strava,
    "evolt": cmd_evolt,
    "audit": cmd_audit,
}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="Training Intelligence ingest")
    ap.add_argument("command", choices=sorted([*COMMANDS, "doctor"]))
    ap.add_argument("--days", type=int, default=7)
    args = ap.parse_args()

    # Diagnosis has to work when the configuration is broken, so it runs
    # before Config.from_env, which raises on the first missing value.
    if args.command == "doctor":
        return cmd_doctor()

    try:
        cfg = Config.from_env()
    except ConfigError as e:
        log.error("%s", e)
        return 2

    try:
        with Db(cfg) as db:
            COMMANDS[args.command](cfg, db, args)
    except Exception as e:
        log.error("%s failed: %s", args.command, e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
