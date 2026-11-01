-- Row level security. This is personal health data: every table is locked to
-- the owning user, with no anon access and no permissive fallback policy.
--
-- GitHub Actions writes with the service role, which carries BYPASSRLS, so the
-- policies below are what guard the browser. Note that because user_id
-- defaults to auth.uid() and the service role has no auth.uid(), every
-- server-side insert must pass user_id explicitly. engine/ti/db.py does this.

do $$
declare
  t text;
  tables text[] := array[
    'athlete_settings','garmin_daily','garmin_body','activities','evolt_scans',
    'daily_checkin','nutrition_daily','daily_load','daily_readiness',
    'daily_scorecard','weekly_reports','insights','sync_status','races','gear'
  ];
begin
  foreach t in array tables loop
    execute format('alter table %I enable row level security', t);
    execute format('alter table %I force row level security', t);
    execute format('drop policy if exists %I on %I', t || '_owner', t);
    execute format(
      'create policy %I on %I for all to authenticated '
      'using (user_id = auth.uid()) with check (user_id = auth.uid())',
      t || '_owner', t
    );
  end loop;
end $$;

-- Evolt PDFs live in a private bucket. Objects are keyed with the owner's uid
-- as the first path segment, which is what the policy checks.
insert into storage.buckets (id, name, public)
values ('evolt-scans', 'evolt-scans', false)
on conflict (id) do update set public = false;

drop policy if exists evolt_scans_owner on storage.objects;
create policy evolt_scans_owner on storage.objects
  for all
  to authenticated
  using (
    bucket_id = 'evolt-scans'
    and (storage.foldername(name))[1] = auth.uid()::text
  )
  with check (
    bucket_id = 'evolt-scans'
    and (storage.foldername(name))[1] = auth.uid()::text
  );
