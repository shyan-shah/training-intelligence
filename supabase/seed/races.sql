-- Race targets from the brief. Dates for 2027 events are provisional.
insert into races (user_id, name, race_date, distance, priority, notes) values
  (auth.uid(), 'London Marathon',  '2027-04-25', 'marathon', 'B', 'Possible, ballot dependent'),
  (auth.uid(), 'Ironman 70.3',     '2027-07-04', '70.3',     'B', 'Mid 2027, event TBC'),
  (auth.uid(), 'Ironman (full)',   '2027-10-03', 'full',     'A', 'Target race')
on conflict do nothing;
