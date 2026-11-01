"""Thin PostgREST client for the Vault Supabase project.

Deliberately not the supabase-py SDK: this needs four verbs, and a direct
client keeps the dependency surface to httpx.

Every write passes user_id explicitly. The table defaults use auth.uid(),
which is null under the service role, so relying on the default would insert
null and fail the not-null constraint.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any, Iterable, Sequence

import httpx

from .config import Config

log = logging.getLogger(__name__)
TIMEOUT = httpx.Timeout(30.0, connect=10.0)


def _encode(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


class Db:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.base = f"{cfg.supabase_url}/rest/v1"
        self._client = httpx.Client(
            timeout=TIMEOUT,
            headers={
                "apikey": cfg.supabase_service_key,
                "Authorization": f"Bearer {cfg.supabase_service_key}",
                "Content-Type": "application/json",
            },
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Db":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- reads --------------------------------------------------------------
    def select(self, table: str, *, columns: str = "*", order: str | None = None,
               limit: int | None = None, **filters: str) -> list[dict]:
        params: dict[str, str] = {"select": columns, "user_id": f"eq.{self.cfg.user_id}"}
        if order:
            params["order"] = order
        if limit:
            params["limit"] = str(limit)
        params.update(filters)
        r = self._client.get(f"{self.base}/{table}", params=params)
        self._raise(r, f"select {table}")
        return r.json()

    def one(self, table: str, **filters: str) -> dict | None:
        rows = self.select(table, limit=1, **filters)
        return rows[0] if rows else None

    # -- writes -------------------------------------------------------------
    def upsert(self, table: str, rows: Sequence[dict], *, on_conflict: str | None = None) -> int:
        """Insert or update. Returns the number of rows sent.

        Chunked, because a 90-day backfill of activities in one request can
        exceed the request size limit.
        """
        if not rows:
            return 0

        payload = [
            {**{k: _encode(v) for k, v in row.items()}, "user_id": self.cfg.user_id}
            for row in rows
        ]

        sent = 0
        for chunk in _chunks(payload, 500):
            params = {"on_conflict": on_conflict} if on_conflict else {}
            r = self._client.post(
                f"{self.base}/{table}",
                params=params,
                content=json.dumps(chunk),
                headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
            )
            self._raise(r, f"upsert {table}")
            sent += len(chunk)
        log.info("upserted %d rows into %s", sent, table)
        return sent

    def update(self, table: str, values: dict, **filters: str) -> None:
        params: dict[str, str] = {"user_id": f"eq.{self.cfg.user_id}"}
        params.update(filters)
        r = self._client.patch(
            f"{self.base}/{table}",
            params=params,
            content=json.dumps({k: _encode(v) for k, v in values.items()}),
            headers={"Prefer": "return=minimal"},
        )
        self._raise(r, f"update {table}")

    def delete(self, table: str, **filters: str) -> None:
        params: dict[str, str] = {"user_id": f"eq.{self.cfg.user_id}"}
        params.update(filters)
        r = self._client.delete(f"{self.base}/{table}", params=params,
                                headers={"Prefer": "return=minimal"})
        self._raise(r, f"delete {table}")

    # -- helpers ------------------------------------------------------------
    def settings(self) -> dict:
        row = self.one("athlete_settings")
        if not row:
            raise RuntimeError(
                "athlete_settings has no row. Run supabase/seed/athlete_settings.sql first."
            )
        return row

    def mark_sync(self, source: str, *, ok: bool, error: str | None = None,
                  token_expires_at: datetime | None = None) -> None:
        """Record the outcome of an ingest run so the page can show a real
        'last synced' stamp per source instead of silently old numbers."""
        now = datetime.now().astimezone()
        values: dict[str, Any] = {"source": source, "last_attempt": now}
        if ok:
            values["last_success"] = now
            values["last_error"] = None
        else:
            values["last_error"] = (error or "")[:500]
        if token_expires_at:
            values["token_expires_at"] = token_expires_at
        self.upsert("sync_status", [values], on_conflict="user_id,source")

    @staticmethod
    def _raise(r: httpx.Response, what: str) -> None:
        if r.status_code >= 400:
            # Never log the key; httpx keeps it in headers, not the body.
            raise RuntimeError(f"{what} failed: HTTP {r.status_code} {r.text[:400]}")


def _chunks(items: Sequence[dict], size: int) -> Iterable[Sequence[dict]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]
