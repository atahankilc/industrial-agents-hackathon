-- One row per Guide conversation: everything a serverless instance needs to continue it (backend/persistence.py).
-- `version` is the optimistic-concurrency counter: a save only succeeds if nobody saved in between.
create table if not exists public.conversations (
    id          text primary key,
    building    text        not null,
    state       jsonb       not null,
    version     integer     not null default 1,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

-- Only the backend (direct Postgres connection) touches this table. RLS without policies keeps the public Data API
-- (anon / publishable key) out of it.
alter table public.conversations enable row level security;
