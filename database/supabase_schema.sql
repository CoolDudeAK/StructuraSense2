-- StructuraSense -> Supabase (Postgres) schema. Run once in Supabase: SQL Editor -> paste -> Run.
-- Generated from the app's real mirror column list (backend/services/cloud_sync.py).
-- Raw readings and waveform samples are NOT mirrored (volume); only summaries/features.

create table if not exists public.structures (
  id text primary key,
  name text,
  kind text,
  location text,
  state text,
  lat double precision,
  lon double precision,
  built_year bigint,
  material text,
  span_m double precision,
  owner_agency text,
  description text,
  is_demo bigint,
  data_mode text,
  limits_json text,
  created_ms bigint
);

create table if not exists public.zones (
  id text primary key,
  structure_id text,
  idx bigint,
  name text,
  x0 double precision,
  x1 double precision
);
create index if not exists idx_zones_structure on public.zones(structure_id);

create table if not exists public.devices (
  id text primary key,
  structure_id text,
  zone_id text,
  name text,
  kind text,
  channel text,
  unit text,
  source_type text,
  pos_x double precision,
  pos_y double precision,
  fs double precision,
  config_json text,
  last_seen_ms bigint,
  created_ms bigint
);
create index if not exists idx_devices_structure on public.devices(structure_id);

create table if not exists public.health_scores (
  id text primary key,
  structure_id text,
  ts_ms bigint,
  score double precision,
  band text,
  coverage double precision,
  components_json text,
  zones_json text,
  method text,
  data_mode text
);
create index if not exists idx_health_scores_structure on public.health_scores(structure_id);

create table if not exists public.alerts (
  id text primary key,
  structure_id text,
  zone_id text,
  device_id text,
  ts_ms bigint,
  severity text,
  kind text,
  title text,
  message text,
  value double precision,
  threshold double precision,
  status text,
  origin text,
  dedupe_key text,
  ack_by text,
  ack_ms bigint,
  resolved_by text,
  resolved_ms bigint,
  resolution_note text
);
create index if not exists idx_alerts_structure on public.alerts(structure_id);

create table if not exists public.crack_analyses (
  id text primary key,
  structure_id text,
  zone_id text,
  ts_ms bigint,
  filename text,
  img_w bigint,
  img_h bigint,
  scale_px_per_mm double precision,
  crack_area_pct double precision,
  length_px double precision,
  max_width_px double precision,
  mean_width_px double precision,
  length_mm double precision,
  max_width_mm double precision,
  mean_width_mm double precision,
  segments bigint,
  severity text,
  crack_detected bigint,
  method text,
  ridge_strength double precision,
  origin text
);
create index if not exists idx_crack_analyses_structure on public.crack_analyses(structure_id);

create table if not exists public.maintenance_tasks (
  id text primary key,
  structure_id text,
  zone_id text,
  created_ms bigint,
  title text,
  description text,
  priority text,
  status text,
  due_date text,
  est_cost_inr bigint,
  origin_alert_id text,
  proposed_by text,
  signed_off_by text,
  signed_off_ms bigint
);
create index if not exists idx_maintenance_tasks_structure on public.maintenance_tasks(structure_id);

create table if not exists public.waveforms (
  id text primary key,
  device_id text,
  structure_id text,
  ts_ms bigint,
  fs double precision,
  n bigint,
  source text,
  rms double precision,
  peak double precision,
  crest double precision,
  kurtosis double precision,
  dom_freq double precision,
  centroid double precision,
  damping double precision,
  bands_json text,
  is_baseline bigint,
  label text,
  notes text
);
create index if not exists idx_waveforms_structure on public.waveforms(structure_id);

-- Security: the app uploads with the service_role key, which bypasses row-level security.
-- Turn RLS on so the public 'anon' key can read nothing until YOU add policies:
alter table public.structures enable row level security;
alter table public.zones enable row level security;
alter table public.devices enable row level security;
alter table public.health_scores enable row level security;
alter table public.alerts enable row level security;
alter table public.crack_analyses enable row level security;
alter table public.maintenance_tasks enable row level security;
alter table public.waveforms enable row level security;

-- Example (optional): let signed-in users read health scores
-- create policy "read health" on public.health_scores for select to authenticated using (true);
