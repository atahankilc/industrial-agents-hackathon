-- Plan import (backend/drafts.py, archive/hackathon/superpowers/specs/2026-10-25-plan-import-design.md): the building the Creator
-- made from floor plans, the private base `import/<id>` of one draft until the user saves it as a building.
create table if not exists public.builder_imports (
    id          text        primary key,
    building    jsonb       not null,
    created_at  timestamptz not null default now()
);

-- Only the backend (direct Postgres connection) touches this table; RLS without policies keeps the Data API out.
alter table public.builder_imports enable row level security;
