create table if not exists public.clipo_users (
  id text primary key,
  email text not null default '',
  name text not null default '',
  display_name text not null default '',
  bio text not null default '',
  picture text not null default '',
  created_at timestamptz not null default now(),
  last_login timestamptz not null default now()
);

alter table public.clipo_users disable row level security;

grant select, insert, update on table public.clipo_users to anon, authenticated;