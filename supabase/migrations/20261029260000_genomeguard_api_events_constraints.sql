-- Align pre-existing live api_events table with the constraints declared by the clean-install migration.
-- The live table was created before the complete migration sequence was checked in.
do $migration$
begin
  if not exists (select 1 from pg_constraint where conrelid='genomeguard.api_events'::regclass and conname='api_events_event_type_check') then
    alter table genomeguard.api_events add constraint api_events_event_type_check
      check (length(trim(event_type)) between 1 and 120) not valid;
    alter table genomeguard.api_events validate constraint api_events_event_type_check;
  end if;
  if not exists (select 1 from pg_constraint where conrelid='genomeguard.api_events'::regclass and conname='api_events_outcome_check') then
    alter table genomeguard.api_events add constraint api_events_outcome_check
      check (length(trim(outcome)) between 1 and 120) not valid;
    alter table genomeguard.api_events validate constraint api_events_outcome_check;
  end if;
  if not exists (select 1 from pg_constraint where conrelid='genomeguard.api_events'::regclass and conname='api_events_details_check') then
    alter table genomeguard.api_events add constraint api_events_details_check
      check (jsonb_typeof(details)='object') not valid;
    alter table genomeguard.api_events validate constraint api_events_details_check;
  end if;
end
$migration$;