-- An organisation's maps (backend/api/maps.py, docs/product/organizations.md phase 2): a named set of buildings with
-- its own address and visibility. `token` is the share link's key for visibility 'link' (kept so editors can copy the
-- link again; a new one shuts out the old link). `buildings`: building ids in order; `layout`: phase 3 (sites).
create table if not exists public.maps (
    slug        text        primary key,
    org         text        not null references public.orgs (slug) on delete cascade,
    name        text        not null,
    visibility  text        not null default 'private' check (visibility in ('private', 'link', 'public')),
    token       text,
    buildings   jsonb       not null default '[]',
    layout      jsonb       not null default '{}',
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);
create index if not exists maps_org on public.maps (org);

-- Only the backend (direct Postgres connection) touches this table; RLS without policies keeps the Data API out.
alter table public.maps enable row level security;
