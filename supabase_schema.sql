-- Supabase schema for EDI App

create table if not exists users (
  id uuid primary key default gen_random_uuid(),
  email text unique not null,
  password_hash text not null,
  role text not null check (role in ('admin','collector')),
  created_at timestamp with time zone default now()
);

-- A global counter for auto-numbering (safe via Postgres sequence)
create sequence if not exists applicant_autonum start 1 increment 1;

create table if not exists applicants (
  id uuid primary key default gen_random_uuid(),
  auto_number bigint not null default nextval('applicant_autonum'),
  -- Core location/admin fields
  region text not null,
  zone text not null,
  woreda text not null,
  kebele text not null,
  batch text not null,
  -- Identity
  first_name text not null,
  father_name text not null,
  grandfather_name text not null,
  date_of_birth date not null,
  sex text not null check (sex in ('m','f')),
  applicant_address text not null,
  -- Business licensing
  has_business_license boolean not null,
  trade_license_number text,
  trade text,
  registration_number text,
  tin_number text,
  date_of_business_license date,
  -- Enterprise
  enterprise_category text not null check (enterprise_category in ('micro','small','medium','startup')),
  ownership_form text not null check (ownership_form in ('soleproprietorship','partnership','plc')),
  business_sector text not null check (business_sector in ('manufacturing','construction','agriculture','mining','service','others')),
  number_of_owners int not null,
  owners_names text not null,
  registered_address text not null,
  business_premise text not null check (business_premise in ('rented','applicant_owned','government')),
  male_employees int not null,
  female_employees int not null,
  total_employees int generated always as (male_employees + female_employees) stored,
  business_capital_etb numeric(18,2) not null,
  monthly_revenue_etb numeric(18,2) not null,
  annual_revenue_last3 numeric(18,2) not null,
  net_profit_last3 numeric(18,2) not null,
  financing_required_etb numeric(18,2) not null,
  source_of_repayment text not null,
  purpose_of_funds text not null,
  -- Guarantee
  guarantor_first_name text not null,
  guarantor_father_name text not null,
  guarantor_grandfather_name text not null,
  guarantor_phone text not null,
  guarantor_monthly_income numeric(18,2) not null,
  -- Banking
  credit_history text not null,
  cbe_account_number text not null,
  cbe_branch text not null,
  cbe_city text not null,
  mode_of_finance text not null check (mode_of_finance in ('conventional','ifb')),
  -- Audit
  collected_by uuid,
  date_collected date not null,
  created_at timestamp with time zone default now()
);

-- Basic RLS: by default locked down
alter table applicants enable row level security;
create policy collectors_insert on applicants for insert
with check (true);

-- Prevent updates by non-admins (admin will use service role bypassing RLS)
create policy read_all on applicants for select using (true);

-- Admin table editor is done via service role key.
