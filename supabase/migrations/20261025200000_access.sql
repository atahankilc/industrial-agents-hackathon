-- Access mode (backend/access.py, docs/superpowers/specs/2026-10-25-access-profiles-design.md).
-- Per building: whether it is public, and rules restricting spaces to groups:
-- rules = {"room_types": {"server_room": ["it"]}, "spaces": {"<space id>": ["public"]}}.
create table if not exists public.access_buildings (
    building    text        primary key,
    public      boolean     not null default true,
    rules       jsonb       not null default '{}',
    updated_at  timestamptz not null default now()
);

-- Members the admin invited: a Supabase Auth user's groups in one building.
create table if not exists public.access_members (
    user_id     text        not null,
    email       text        not null,
    building    text        not null,
    groups      jsonb       not null default '[]',
    updated_at  timestamptz not null default now(),
    primary key (user_id, building)
);

-- Only the backend (direct Postgres connection) touches these tables. RLS without policies keeps the public Data API
-- (anon / publishable key) out of them.
alter table public.access_buildings enable row level security;
alter table public.access_members enable row level security;

-- A signed-in user's remembered preferences: {"remember", "auto_capture", "global": {...}, "buildings": {id: {...}}}.
create table if not exists public.user_preferences (
    user_id      text        primary key,
    preferences  jsonb       not null default '{}',
    updated_at   timestamptz not null default now()
);
alter table public.user_preferences enable row level security;

-- Moving objects (backend/fleet.py): attributes, the device token's hash, latest position + trail, current mission.
create table if not exists public.fleet_objects (
    id          text        primary key,
    building    text        not null,
    name        text        not null,
    kind        text        not null,
    attributes  jsonb       not null,
    token_hash  text        not null,
    position    jsonb,
    trail       jsonb       not null default '[]',
    mission     jsonb,
    updated_at  timestamptz not null default now()
);
create index if not exists fleet_objects_building on public.fleet_objects (building);
alter table public.fleet_objects enable row level security;
