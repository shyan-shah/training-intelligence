-- Race targets from the brief. The 2027 dates are provisional.
--
-- EDIT THE EMAIL BELOW. Same reason as athlete_settings.sql: auth.uid() is
-- NULL when SQL is run as an admin rather than through a request.

do $$
declare
  owner_email constant text := 'shyansshah@gmail.com';   -- <<< EDIT THIS
  owner_id    uuid;
begin
  select id into owner_id from auth.users where email = owner_email;

  if owner_id is null then
    raise exception
      'No auth user with email %. Create it under Authentication > Users, then run this again.',
      owner_email;
  end if;

  insert into races (user_id, name, race_date, distance, priority, notes)
  select owner_id, name, race_date, distance, priority, notes
  from (values
    ('London Marathon', date '2027-04-25', 'marathon', 'B', 'Possible, ballot dependent'),
    ('Ironman 70.3',    date '2027-07-04', '70.3',     'B', 'Mid 2027, event TBC'),
    ('Ironman (full)',  date '2027-10-03', 'full',     'A', 'Target race')
  ) as r(name, race_date, distance, priority, notes)
  where not exists (
    select 1 from races existing
    where existing.user_id = owner_id and existing.name = r.name
  );

  raise notice 'Seeded races for %', owner_email;
end $$;
