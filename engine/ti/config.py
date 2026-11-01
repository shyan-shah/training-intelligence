"""Configuration, read from the environment only.

Secrets never appear in code, commits or logs. Every value here comes from a
GitHub Actions secret in CI or a gitignored .env locally.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

LONDON = "Europe/London"


class ConfigError(RuntimeError):
    pass


def _req(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise ConfigError(f"{name} is not set. See .env.example.")
    return v


def _opt(name: str) -> str | None:
    return os.environ.get(name) or None


@dataclass(frozen=True)
class Config:
    supabase_url: str
    supabase_service_key: str
    user_id: str

    garmin_personal_token: str | None = None
    garmin_email: str | None = None
    garmin_password: str | None = None

    strava_client_id: str | None = None
    strava_client_secret: str | None = None
    strava_refresh_token: str | None = None

    anthropic_api_key: str | None = None      # Evolt vision fallback only

    ntfy_topic: str | None = None
    ntfy_include_sensitive: bool = False

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            supabase_url=_req("SUPABASE_URL").rstrip("/"),
            supabase_service_key=_req("SUPABASE_SERVICE_KEY"),
            user_id=_req("TI_USER_ID"),
            garmin_personal_token=_opt("GARMIN_PERSONAL_TOKEN"),
            garmin_email=_opt("GARMIN_EMAIL"),
            garmin_password=_opt("GARMIN_PASSWORD"),
            strava_client_id=_opt("STRAVA_CLIENT_ID"),
            strava_client_secret=_opt("STRAVA_CLIENT_SECRET"),
            strava_refresh_token=_opt("STRAVA_REFRESH_TOKEN"),
            anthropic_api_key=_opt("ANTHROPIC_API_KEY"),
            ntfy_topic=_opt("NTFY_TOPIC"),
            # Defaults to off. Health numbers must never reach the public relay.
            ntfy_include_sensitive=os.environ.get("NTFY_INCLUDE_SENSITIVE", "0") == "1",
        )
