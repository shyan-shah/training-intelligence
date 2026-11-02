#!/usr/bin/env bash
#
# Runs the migrations and seeds against a throwaway Postgres and asserts the
# things that are easy to get wrong and expensive to get wrong in production:
# that the DDL is valid, that the seeds work the way the README says to run
# them, and that RLS actually isolates users.
#
# It earned its place immediately. The seeds used to call auth.uid(), which is
# NULL when SQL is run as an admin rather than through a request, so they
# failed on a not-null violation the first time anyone followed the setup
# steps.
#
#   ./supabase/test/run.sh
#
# Needs a local Postgres 16 (server binaries, not just psql). Nothing touches
# the real project.
set -euo pipefail

PGBIN=${PGBIN:-/usr/lib/postgresql/16/bin}
PGPORT=${PGPORT:-55433}
TMPDIR_=$(mktemp -d)
SOCK="$TMPDIR_/sock"
DATA="$TMPDIR_/data"
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)

mkdir -p "$SOCK" "$DATA"

# initdb refuses to run as root, so drop to an unprivileged user if we are.
RUNAS=""
if [ "$(id -u)" = "0" ]; then
  id -u pgtest >/dev/null 2>&1 || useradd -m pgtest
  chown -R pgtest:pgtest "$TMPDIR_"
  RUNAS="su pgtest -c"
fi

run() { if [ -n "$RUNAS" ]; then su pgtest -c "$1"; else bash -c "$1"; fi; }

cleanup() {
  run "$PGBIN/pg_ctl -D $DATA stop -m immediate" >/dev/null 2>&1 || true
  rm -rf "$TMPDIR_"
}
trap cleanup EXIT

run "$PGBIN/initdb -D $DATA -U postgres --auth=trust" >/dev/null
run "$PGBIN/pg_ctl -D $DATA -o '-p $PGPORT -k $SOCK' -l $TMPDIR_/pg.log start" >/dev/null
sleep 2

PSQL="psql -h $SOCK -p $PGPORT -U postgres -v ON_ERROR_STOP=1 -tAq"

fails=0
check() { # check <name> <actual> <expected>
  if [ "$2" = "$3" ]; then
    printf 'PASS %s\n' "$1"
  else
    printf 'FAIL %s (got %s, want %s)\n' "$1" "$2" "$3"
    fails=$((fails + 1))
  fi
}

$PSQL -c "create database ti;" >/dev/null
$PSQL -d ti -f "$HERE/stub.sql" >/dev/null
echo "PASS supabase stubs"

$PSQL -d ti -f "$ROOT/supabase/migrations/0001_init.sql" >/dev/null
echo "PASS migration 0001"
$PSQL -d ti -f "$ROOT/supabase/migrations/0002_rls.sql" >/dev/null 2>&1
echo "PASS migration 0002"

# Every table must have RLS on, forced, and exactly one owner policy.
unprotected=$($PSQL -d ti -c "
  select count(*) from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
  where n.nspname = 'public' and c.relkind = 'r'
    and (not c.relrowsecurity or not c.relforcerowsecurity);")
check "every public table has RLS enabled and forced" "$unprotected" "0"

nopolicy=$($PSQL -d ti -c "
  select count(*) from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
  where n.nspname = 'public' and c.relkind = 'r'
    and not exists (select 1 from pg_policy p where p.polrelid = c.oid);")
check "every public table has a policy" "$nopolicy" "0"

# The seed must fail loudly before the auth user exists.
if $PSQL -d ti -f "$ROOT/supabase/seed/athlete_settings.sql" >/dev/null 2>&1; then
  echo "FAIL seed should refuse to run before the auth user exists"
  fails=$((fails + 1))
else
  echo "PASS seed refuses to run before the auth user exists"
fi

OWNER=$($PSQL -d ti -c "insert into auth.users (email) values ('owner@example.test') returning id;")
OTHER=$($PSQL -d ti -c "insert into auth.users (email) values ('other@example.test') returning id;")

# Seeds use a hardcoded email, so point them at the test user.
sed "s/shyansshah@gmail.com/owner@example.test/" "$ROOT/supabase/seed/athlete_settings.sql" \
  | $PSQL -d ti >/dev/null
sed "s/shyansshah@gmail.com/owner@example.test/" "$ROOT/supabase/seed/races.sql" \
  | $PSQL -d ti >/dev/null
echo "PASS seeds applied"

# And again, to prove they are idempotent.
sed "s/shyansshah@gmail.com/owner@example.test/" "$ROOT/supabase/seed/athlete_settings.sql" \
  | $PSQL -d ti >/dev/null
sed "s/shyansshah@gmail.com/owner@example.test/" "$ROOT/supabase/seed/races.sql" \
  | $PSQL -d ti >/dev/null

check "settings is one row after two seed runs" \
  "$($PSQL -d ti -c 'select count(*) from athlete_settings;')" "1"
check "races is three rows after two seed runs" \
  "$($PSQL -d ti -c 'select count(*) from races;')" "3"
check "protein target is 216" \
  "$($PSQL -d ti -c "select targets->>'protein_g' from athlete_settings;")" "216"

$PSQL -d ti -c "
  grant usage on schema public to authenticated, service_role;
  grant all on all tables in schema public to authenticated, service_role;" >/dev/null

check "owner sees their settings" "$($PSQL -d ti <<SQL
set role authenticated;
set request.jwt.claim.sub = '$OWNER';
select count(*) from athlete_settings;
SQL
)" "1"

check "another signed-in user sees nothing" "$($PSQL -d ti <<SQL
set role authenticated;
set request.jwt.claim.sub = '$OTHER';
select count(*) from athlete_settings;
SQL
)" "0"

if $PSQL -d ti >/dev/null 2>&1 <<SQL
set role authenticated;
set request.jwt.claim.sub = '$OTHER';
insert into daily_checkin (user_id, day, energy) values ('$OWNER', current_date, 5);
SQL
then
  echo "FAIL a user must not write a row owned by someone else"
  fails=$((fails + 1))
else
  echo "PASS a user cannot write a row owned by someone else"
fi

# The ingest runs as service_role. FORCE RLS must not lock it out.
check "service_role reads every row" "$($PSQL -d ti <<SQL
set role service_role;
select count(*) from athlete_settings;
SQL
)" "1"

check "service_role can write" "$($PSQL -d ti <<SQL
set role service_role;
insert into garmin_daily (user_id, day, hrv_night) values ('$OWNER', current_date, 61);
select count(*) from garmin_daily;
SQL
)" "1"

echo
if [ "$fails" -eq 0 ]; then
  echo "All database checks clean."
else
  echo "$fails database check(s) failed."
  exit 1
fi
