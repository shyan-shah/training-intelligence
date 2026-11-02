"""Upserts must not mix key sets in one request.

PostgREST answers a bulk insert whose objects differ in their keys with
PGRST102 "All object keys must match". A 7-day Garmin pull hits this the
moment one day has sleep data and the next does not.
"""
import json

from ti.db import Db, _by_key_signature
from ti.config import Config

CFG = Config(
    supabase_url="https://example.supabase.co",
    supabase_service_key="service-key",
    user_id="11111111-2222-3333-4444-555555555555",
)


class _FakeResponse:
    status_code = 201
    text = ""

    def json(self) -> list:
        return []


class _FakeClient:
    """Records every POST body instead of sending it."""

    def __init__(self) -> None:
        self.bodies: list[list[dict]] = []

    def post(self, url, *, params, content, headers):
        self.bodies.append(json.loads(content))
        return _FakeResponse()

    def close(self) -> None:
        pass


def _db() -> tuple[Db, _FakeClient]:
    db = Db(CFG)
    db.close()
    client = _FakeClient()
    db._client = client
    return db, client


def test_groups_rows_by_key_signature():
    rows = [
        {"day": "2026-11-01", "steps": 900},
        {"day": "2026-11-02", "steps": 800, "sleep_score": 71},
        {"day": "2026-11-03", "steps": 700},
    ]
    groups = _by_key_signature(rows)

    assert len(groups) == 2
    assert [len(g) for g in groups] == [2, 1]
    for group in groups:
        assert len({frozenset(r) for r in group}) == 1


def test_upsert_sends_one_request_per_shape():
    db, client = _db()

    sent = db.upsert(
        "garmin_daily",
        [
            {"day": "2026-11-01", "steps": 900},
            {"day": "2026-11-02", "steps": 800, "sleep_score": 71},
            {"day": "2026-11-03", "steps": 700},
        ],
        on_conflict="user_id,day",
    )

    assert sent == 3
    assert len(client.bodies) == 2
    for body in client.bodies:
        assert len({frozenset(r) for r in body}) == 1


def test_upsert_never_pads_missing_keys_with_null():
    """Padding would erase stored values: merge-duplicates writes every
    column it is given, so a null for a briefly unavailable source would
    overwrite yesterday's good reading."""
    db, client = _db()

    db.upsert(
        "garmin_daily",
        [
            {"day": "2026-11-01", "steps": 900},
            {"day": "2026-11-02", "steps": 800, "sleep_score": 71},
        ],
        on_conflict="user_id,day",
    )

    for body in client.bodies:
        for row in body:
            assert "sleep_score" not in row or row["sleep_score"] is not None


def test_upsert_still_stamps_user_id():
    db, client = _db()

    db.upsert("garmin_daily", [{"day": "2026-11-01", "steps": 900}])

    assert client.bodies[0][0]["user_id"] == CFG.user_id


def test_upsert_of_uniform_rows_is_a_single_request():
    db, client = _db()

    db.upsert(
        "garmin_daily",
        [{"day": "2026-11-01", "steps": 900}, {"day": "2026-11-02", "steps": 800}],
    )

    assert len(client.bodies) == 1
