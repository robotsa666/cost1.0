-- Supabase / PostgreSQL schema
create extension if not exists ltree;

create table if not exists periods (
  id            bigserial primary key,
  code          text not null unique,
  start_date    date not null,
  end_date      date not null,
  check (start_date <= end_date)
);

create table if not exists scenarios (
  id            bigserial primary key,
  code          text not null unique,
  name          text not null
);

create table if not exists accounts (
  id            bigserial primary key,
  code          text not null unique,
  name          text not null,
  parent_code   text references accounts(code) on update cascade on delete set null,
  path          ltree,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

create index if not exists idx_accounts_path_gist on accounts using gist (path);
create index if not exists idx_accounts_parent_code on accounts(parent_code);

create or replace function trg_accounts_set_path()
returns trigger language plpgsql as $$
declare
  parent_path ltree;
begin
  new.updated_at := now();

  if new.parent_code is null then
    new.path := text2ltree(new.code);
  else
    select path into parent_path from accounts where code = new.parent_code;
    if parent_path is null then
      raise exception 'Parent account % not found or has no path', new.parent_code;
    end if;
    new.path := parent_path || text2ltree(new.code);
  end if;

  return new;
end;
$$;

drop trigger if exists trg_accounts_set_path_iud on accounts;
create trigger trg_accounts_set_path_iud
before insert or update of code, parent_code
on accounts
for each row
execute function trg_accounts_set_path();

create table if not exists initial_costs (
  id            bigserial primary key,
  period_id     bigint not null references periods(id) on delete restrict,
  scenario_id   bigint not null references scenarios(id) on delete restrict,
  account_code  text not null references accounts(code) on update cascade on delete restrict,
  amount        numeric(18,6) not null default 0,
  source        text default 'import',
  created_at    timestamptz not null default now(),
  unique (period_id, scenario_id, account_code)
);

create index if not exists idx_initial_costs_period_scen on initial_costs(period_id, scenario_id);
create index if not exists idx_initial_costs_account on initial_costs(account_code);

create table if not exists allocation_models (
  id            bigserial primary key,
  code          text not null unique,
  name          text not null,
  is_active     boolean not null default true,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

create table if not exists allocation_rules (
  id            bigserial primary key,
  model_id      bigint not null references allocation_models(id) on delete cascade,
  parent_code   text not null references accounts(code) on update cascade on delete restrict,
  child_code    text not null references accounts(code) on update cascade on delete restrict,
  weight        numeric(18,6) not null check (weight >= 0),
  created_at    timestamptz not null default now(),
  unique (model_id, parent_code, child_code)
);

create index if not exists idx_rules_model_parent on allocation_rules(model_id, parent_code);
create index if not exists idx_rules_model_child on allocation_rules(model_id, child_code);

create or replace view v_rules_normalized as
select
  r.model_id,
  r.parent_code,
  r.child_code,
  case when sum_w = 0 then 0 else r.weight / sum_w end as w_norm
from (
  select
    model_id, parent_code, sum(weight) over (partition by model_id, parent_code) as sum_w,
    child_code, weight
  from allocation_rules
) r;

create table if not exists allocation_runs (
  id            bigserial primary key,
  model_id      bigint not null references allocation_models(id) on delete restrict,
  period_id     bigint not null references periods(id) on delete restrict,
  scenario_id   bigint not null references scenarios(id) on delete restrict,
  started_at    timestamptz not null default now(),
  finished_at   timestamptz,
  status        text not null default 'running',
  message       text,
  unique (model_id, period_id, scenario_id, started_at)
);

create table if not exists allocation_postings (
  id            bigserial primary key,
  run_id        bigint not null references allocation_runs(id) on delete cascade,
  parent_code   text not null references accounts(code) on update cascade on delete restrict,
  child_code    text not null references accounts(code) on update cascade on delete restrict,
  amount        numeric(18,6) not null,
  iter_no       integer not null default 1,
  created_at    timestamptz not null default now()
);

create index if not exists idx_postings_run on allocation_postings(run_id);
create index if not exists idx_postings_parent on allocation_postings(parent_code);
create index if not exists idx_postings_child on allocation_postings(child_code);

create table if not exists allocation_results (
  id            bigserial primary key,
  run_id        bigint not null references allocation_runs(id) on delete cascade,
  account_code  text not null references accounts(code) on update cascade on delete restrict,
  amount        numeric(18,6) not null,
  created_at    timestamptz not null default now(),
  unique (run_id, account_code)
);

create index if not exists idx_results_run on allocation_results(run_id);
create index if not exists idx_results_account on allocation_results(account_code);

create or replace view v_accounts as
select a.id, a.code, a.name, a.parent_code, nlevel(a.path) as depth, a.path
from accounts a;

create or replace view v_initial_costs as
select period_id, scenario_id, account_code, sum(amount) as amount
from initial_costs
group by period_id, scenario_id, account_code;

-- seed data
insert into periods (code, start_date, end_date)
values ('2025M08', date '2025-08-01', date '2025-08-31')
on conflict (code) do nothing;

insert into scenarios (code, name)
values ('BASE', 'Scenariusz bazowy')
on conflict (code) do nothing;

insert into accounts (code, name, parent_code) values
  ('100','Koszty ogólne',null),
  ('110','Utrzymanie biura','100'),
  ('120','IT','100'),
  ('121','Helpdesk','120'),
  ('122','Infrastruktura','120')
on conflict (code) do nothing;

insert into initial_costs (period_id, scenario_id, account_code, amount)
select p.id, s.id, '100', 100000
from periods p, scenarios s
where p.code='2025M08' and s.code='BASE'
on conflict do nothing;

insert into allocation_models (code, name) values ('MODEL_BASE', 'Model bazowy')
on conflict (code) do nothing;

insert into allocation_rules (model_id, parent_code, child_code, weight)
select m.id, r.parent_code, r.child_code, r.weight
from allocation_models m,
     ( values
       ('100','110', 0.4),
       ('100','120', 0.6),
       ('120','121', 0.3),
       ('120','122', 0.7)
     ) as r(parent_code, child_code, weight)
where m.code='MODEL_BASE'
on conflict do nothing;
