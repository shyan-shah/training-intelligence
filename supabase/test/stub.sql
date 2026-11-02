-- Minimal stand-ins for the Supabase-managed objects the migrations depend on,
-- so the migrations can be run against a plain Postgres.
create role anon nologin;
create role authenticated nologin;
create role service_role nologin bypassrls;

create schema if not exists auth;
create table auth.users (
  id    uuid primary key default gen_random_uuid(),
  email text unique not null
);

-- Supabase derives this from the request JWT. Here it reads a GUC the tests set.
create or replace function auth.uid() returns uuid language sql stable as $$
  select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid;
$$;

create schema if not exists storage;
create table storage.buckets (
  id     text primary key,
  name   text not null,
  public boolean not null default false
);
create table storage.objects (
  id        uuid primary key default gen_random_uuid(),
  bucket_id text references storage.buckets(id),
  name      text not null,
  owner     uuid
);
create or replace function storage.foldername(name text) returns text[]
  language sql immutable as $$ select string_to_array(name, '/'); $$;

grant usage on schema auth, storage to anon, authenticated, service_role;
