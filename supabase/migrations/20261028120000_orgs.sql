-- Organisations (backend/api/access.py, docs/product/organizations.md): an org owns buildings; its people have a
-- role (viewer / editor / owner). A building's listing replaces the public flag: listed (main map), unlisted (opened
-- by link or the org's map), private (the org and invited members only).
create table if not exists public.orgs (
    slug        text        primary key,
    name        text        not null,
    verified    boolean     not null default false,  -- set by an admin; needed to list a building on the main map
    created_by  text,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

create table if not exists public.org_members (
    org         text        not null references public.orgs (slug) on delete cascade,
    user_id     text        not null,
    email       text        not null,
    role        text        not null check (role in ('viewer', 'editor', 'owner')),
    updated_at  timestamptz not null default now(),
    primary key (org, user_id)
);
create index if not exists org_members_user on public.org_members (user_id);

-- `public` stays and is still written: code deployed before this migration reads and writes only it, so the backend
-- trusts `public` when the two disagree (backend/api/access.py building_row). No org = the platform's building.
alter table public.access_buildings add column if not exists listing text
    check (listing in ('listed', 'unlisted', 'private'));
alter table public.access_buildings add column if not exists org text references public.orgs (slug) on delete set null;
update public.access_buildings set listing = case when public then 'listed' else 'private' end where listing is null;

-- Only the backend (direct Postgres connection) touches these tables. RLS without policies keeps the public Data API
-- (anon / publishable key) out of them.
alter table public.orgs enable row level security;
alter table public.org_members enable row level security;
