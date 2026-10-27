-- Kit building ids lose their split prefix (D-028): "train/proc-campus-train-000" -> "proc-campus-train-000"; the
-- dataset now lives in data/buildings/ and the split is only the manifest's `split` column. Saved buildings keep
-- "user/<slug>". Idempotent: rows already on the new ids no longer match.
update public.conversations    set building = regexp_replace(building, '^(train|dev|test)/', '') where building ~ '^(train|dev|test)/';
update public.builder_drafts   set base = regexp_replace(base, '^(train|dev|test)/', '')         where base ~ '^(train|dev|test)/';
update public.saved_buildings  set base = regexp_replace(base, '^(train|dev|test)/', '')         where base ~ '^(train|dev|test)/';
update public.access_buildings set building = regexp_replace(building, '^(train|dev|test)/', '') where building ~ '^(train|dev|test)/';
update public.access_members   set building = regexp_replace(building, '^(train|dev|test)/', '') where building ~ '^(train|dev|test)/';
update public.fleet_objects    set building = regexp_replace(building, '^(train|dev|test)/', '') where building ~ '^(train|dev|test)/';

-- Ids inside JSON (a conversation's events, a saved building's source_ref.base, a draft's steps and Builder chat): only whole string
-- values that are a split plus a kit directory name.
update public.conversations
   set state = regexp_replace(state::text, '"(train|dev|test)/((osm-way|proc-|resplan-|swiss-)[^"]*)"', '"\2"', 'g')::jsonb
 where state::text ~ '"(train|dev|test)/(osm-way|proc-|resplan-|swiss-)';
update public.saved_buildings
   set building = regexp_replace(building::text, '"(train|dev|test)/((osm-way|proc-|resplan-|swiss-)[^"]*)"', '"\2"', 'g')::jsonb,
       steps = regexp_replace(steps::text, '"(train|dev|test)/((osm-way|proc-|resplan-|swiss-)[^"]*)"', '"\2"', 'g')::jsonb
 where building::text ~ '"(train|dev|test)/(osm-way|proc-|resplan-|swiss-)'
    or steps::text ~ '"(train|dev|test)/(osm-way|proc-|resplan-|swiss-)';
update public.builder_drafts
   set steps = regexp_replace(steps::text, '"(train|dev|test)/((osm-way|proc-|resplan-|swiss-)[^"]*)"', '"\2"', 'g')::jsonb,
       builder = regexp_replace(builder::text, '"(train|dev|test)/((osm-way|proc-|resplan-|swiss-)[^"]*)"', '"\2"', 'g')::jsonb
 where steps::text ~ '"(train|dev|test)/(osm-way|proc-|resplan-|swiss-)'
    or builder::text ~ '"(train|dev|test)/(osm-way|proc-|resplan-|swiss-)';
