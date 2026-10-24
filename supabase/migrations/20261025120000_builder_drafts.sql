-- Edit mode (backend/drafts.py): one row per draft, and one per saved building, so any serverless instance can
-- serve any request. `version` / `builder_version` are optimistic-concurrency counters: a save only succeeds if
-- nobody saved in between. `builder` is the Builder agent's conversation (agent/builder.py Builder.dump).
create table if not exists public.builder_drafts (
    id               text        primary key,
    base             text        not null,
    name             text        not null,
    steps            jsonb       not null default '[]',
    version          integer     not null default 0,
    builder          jsonb,
    builder_version  integer     not null default 0,
    created_at       timestamptz not null default now(),
    updated_at       timestamptz not null default now()
);

-- Saved buildings (`user/<slug>` in the catalogue), visible to everyone. The primary key makes claiming a slug atomic.
create table if not exists public.saved_buildings (
    slug        text        primary key,
    name        text        not null,
    base        text        not null,
    building    jsonb       not null,
    steps       jsonb       not null,
    created_at  timestamptz not null default now()
);

-- Only the backend (direct Postgres connection) touches these tables. RLS without policies keeps the public Data API
-- (anon / publishable key) out of them.
alter table public.builder_drafts enable row level security;
alter table public.saved_buildings enable row level security;
