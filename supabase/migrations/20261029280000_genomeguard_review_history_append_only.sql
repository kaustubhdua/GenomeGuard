-- Protect the review history from ordinary UPDATE, DELETE and TRUNCATE operations.
create or replace function genomeguard.reject_immutable_history_mutation()
returns trigger
language plpgsql
set search_path = ''
as $immutable_history$
begin
  raise exception '% is append-only; % is not permitted',
    quote_ident(TG_TABLE_SCHEMA) || '.' || quote_ident(TG_TABLE_NAME), TG_OP
    using errcode = '55000';
end;
$immutable_history$;

drop trigger if exists request_review_history_no_update_delete on genomeguard.request_review_history;
create trigger request_review_history_no_update_delete
  before update or delete on genomeguard.request_review_history
  for each row execute function genomeguard.reject_immutable_history_mutation();
drop trigger if exists request_review_history_no_truncate on genomeguard.request_review_history;
create trigger request_review_history_no_truncate
  before truncate on genomeguard.request_review_history
  for each statement execute function genomeguard.reject_immutable_history_mutation();
