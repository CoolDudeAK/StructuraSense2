-- StructuraSense local database (SQLite). Entity tables use TEXT ids (uuid hex) so they can be
-- mirrored 1:1 to Supabase/Postgres (see supabase_schema.sql). Times are UTC epoch milliseconds.

CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('admin','engineer','viewer')),
  pw_hash TEXT NOT NULL,
  created_ms INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS structures (
  id TEXT PRIMARY KEY,                  -- e.g. STR-001
  name TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('specimen','bridge','flyover','building','dam')),
  location TEXT,
  state TEXT,
  lat REAL, lon REAL,
  built_year INTEGER,
  material TEXT,
  span_m REAL,
  owner_agency TEXT,
  description TEXT,
  is_demo INTEGER NOT NULL DEFAULT 1,   -- 1 = fictional demo asset
  data_mode TEXT NOT NULL DEFAULT 'all' CHECK (data_mode IN ('sim','live','all')),
  limits_json TEXT NOT NULL DEFAULT '{}', -- strain_limit_ue, deflection_ratio, wim_limit_kn, cycles_per_day
  created_ms INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS zones (
  id TEXT PRIMARY KEY,                  -- e.g. STR-001-Z1
  structure_id TEXT NOT NULL REFERENCES structures(id) ON DELETE CASCADE,
  idx INTEGER NOT NULL,
  name TEXT NOT NULL,
  x0 REAL NOT NULL, x1 REAL NOT NULL    -- fraction of structure length (0..1)
);

CREATE TABLE IF NOT EXISTS devices (
  id TEXT PRIMARY KEY,                  -- e.g. piezo-01
  structure_id TEXT NOT NULL REFERENCES structures(id) ON DELETE CASCADE,
  zone_id TEXT REFERENCES zones(id) ON DELETE SET NULL,
  name TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('piezo','accelerometer','microphone','strain','lvdt','temperature','moisture','wim','camera','rf_coil')),
  channel TEXT NOT NULL CHECK (channel IN ('waveform','scalar','image')),
  unit TEXT,
  source_type TEXT NOT NULL DEFAULT 'simulated' CHECK (source_type IN ('simulated','arduino_serial','esp32_http','csv','manual')),
  pos_x REAL, pos_y REAL,               -- position on elevation drawing (0..1)
  fs REAL,                              -- sample rate (waveform devices)
  api_key_hash TEXT,
  config_json TEXT NOT NULL DEFAULT '{}',
  last_seen_ms INTEGER,
  created_ms INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_devices_structure ON devices(structure_id);

CREATE TABLE IF NOT EXISTS readings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  device_id TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
  ts_ms INTEGER NOT NULL,
  value REAL NOT NULL,
  source TEXT NOT NULL CHECK (source IN ('sim','live','file')),
  batch_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_readings_dev_ts ON readings(device_id, ts_ms);

CREATE TABLE IF NOT EXISTS waveforms (
  id TEXT PRIMARY KEY,
  device_id TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
  structure_id TEXT NOT NULL REFERENCES structures(id) ON DELETE CASCADE,
  ts_ms INTEGER NOT NULL,
  fs REAL NOT NULL,
  n INTEGER NOT NULL,
  samples BLOB NOT NULL,                -- float32 little-endian
  source TEXT NOT NULL CHECK (source IN ('sim','live','file')),
  rms REAL, peak REAL, crest REAL, kurtosis REAL,
  dom_freq REAL, centroid REAL, damping REAL,
  bands_json TEXT,
  is_baseline INTEGER NOT NULL DEFAULT 0,
  label TEXT CHECK (label IN ('healthy','damaged') OR label IS NULL),
  notes TEXT,
  sim_damage REAL                       -- ground truth for simulated captures only
);
CREATE INDEX IF NOT EXISTS idx_wave_dev_ts ON waveforms(device_id, ts_ms);

CREATE TABLE IF NOT EXISTS crack_analyses (
  id TEXT PRIMARY KEY,
  structure_id TEXT NOT NULL REFERENCES structures(id) ON DELETE CASCADE,
  zone_id TEXT REFERENCES zones(id) ON DELETE SET NULL,
  ts_ms INTEGER NOT NULL,
  filename TEXT,
  image_file TEXT, overlay_file TEXT,
  img_w INTEGER, img_h INTEGER,
  scale_px_per_mm REAL,                 -- NULL = uncalibrated
  crack_area_pct REAL,
  length_px REAL, max_width_px REAL, mean_width_px REAL,
  length_mm REAL, max_width_mm REAL, mean_width_mm REAL,
  segments INTEGER,
  severity TEXT,
  crack_detected INTEGER NOT NULL DEFAULT 0,
  method TEXT NOT NULL,
  ridge_strength REAL,
  segments_json TEXT,
  origin TEXT NOT NULL DEFAULT 'upload',
  user_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_crack_struct ON crack_analyses(structure_id, ts_ms);

CREATE TABLE IF NOT EXISTS health_scores (
  id TEXT PRIMARY KEY,
  structure_id TEXT NOT NULL REFERENCES structures(id) ON DELETE CASCADE,
  ts_ms INTEGER NOT NULL,
  score REAL NOT NULL,
  band TEXT NOT NULL,
  coverage REAL,
  components_json TEXT NOT NULL,
  zones_json TEXT,
  method TEXT NOT NULL,
  data_mode TEXT
);
CREATE INDEX IF NOT EXISTS idx_health_struct ON health_scores(structure_id, ts_ms);

CREATE TABLE IF NOT EXISTS alerts (
  id TEXT PRIMARY KEY,
  structure_id TEXT NOT NULL REFERENCES structures(id) ON DELETE CASCADE,
  zone_id TEXT, device_id TEXT,
  ts_ms INTEGER NOT NULL,
  severity TEXT NOT NULL CHECK (severity IN ('info','warning','critical')),
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  message TEXT,
  value REAL, threshold REAL,
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','acknowledged','resolved','dismissed','cleared')),
  origin TEXT NOT NULL DEFAULT 'sim',   -- sim | live | file | mixed
  dedupe_key TEXT NOT NULL,
  ack_by TEXT, ack_ms INTEGER,
  resolved_by TEXT, resolved_ms INTEGER, resolution_note TEXT
);
CREATE INDEX IF NOT EXISTS idx_alerts_struct ON alerts(structure_id, status);
CREATE INDEX IF NOT EXISTS idx_alerts_dedupe ON alerts(dedupe_key, status);

CREATE TABLE IF NOT EXISTS maintenance_tasks (
  id TEXT PRIMARY KEY,
  structure_id TEXT NOT NULL REFERENCES structures(id) ON DELETE CASCADE,
  zone_id TEXT,
  created_ms INTEGER NOT NULL,
  title TEXT NOT NULL,
  description TEXT,
  priority TEXT NOT NULL CHECK (priority IN ('P1','P2','P3')),
  status TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed','approved','in_progress','done','rejected')),
  due_date TEXT,
  est_cost_inr INTEGER,
  origin_alert_id TEXT,
  proposed_by TEXT NOT NULL DEFAULT 'rules-engine',
  signed_off_by TEXT, signed_off_ms INTEGER
);

CREATE TABLE IF NOT EXISTS sim_state (
  structure_id TEXT PRIMARY KEY REFERENCES structures(id) ON DELETE CASCADE,
  scenario TEXT NOT NULL DEFAULT 'healthy',
  damage REAL NOT NULL DEFAULT 0,
  moisture_boost REAL NOT NULL DEFAULT 0,
  speed REAL NOT NULL DEFAULT 0,        -- damage per second while degrading
  updated_ms INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_ms INTEGER NOT NULL,
  user_id TEXT, user_name TEXT,
  action TEXT NOT NULL,
  entity TEXT, entity_id TEXT,
  detail TEXT
);

CREATE TABLE IF NOT EXISTS csv_imports (
  id TEXT PRIMARY KEY,
  ts_ms INTEGER NOT NULL,
  structure_id TEXT, filename TEXT,
  mode TEXT, rows_total INTEGER, rows_ok INTEGER, rows_rejected INTEGER,
  user_id TEXT
);

CREATE TABLE IF NOT EXISTS sync_queue (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  table_name TEXT NOT NULL,
  row_id TEXT NOT NULL,
  created_ms INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','done','failed')),
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  UNIQUE(table_name, row_id, status)
);

-- ---- Impact Lab: the real Arduino + 3 piezo specimen workflow (ported from the Streamlit prototype) ----
CREATE TABLE IF NOT EXISTS impact_baselines (
  structure_id TEXT PRIMARY KEY REFERENCES structures(id) ON DELETE CASCADE,
  s1_mean REAL, s1_std REAL, s2_mean REAL, s2_std REAL, s3_mean REAL, s3_std REAL,
  num_trials INTEGER, specimen_id TEXT, created_ms INTEGER,
  source TEXT                           -- live | sim | mixed : what kind of data the baseline came from
);

CREATE TABLE IF NOT EXISTS impact_calibration (   -- staging area while recording baseline trials
  id TEXT PRIMARY KEY,
  structure_id TEXT NOT NULL REFERENCES structures(id) ON DELETE CASCADE,
  ts_ms INTEGER NOT NULL,
  s1 REAL, s2 REAL, s3 REAL,
  source TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS impact_trials (
  id TEXT PRIMARY KEY,
  structure_id TEXT NOT NULL REFERENCES structures(id) ON DELETE CASCADE,
  ts_ms INTEGER NOT NULL,
  condition TEXT NOT NULL CHECK (condition IN ('Intact','Damaged')),
  s1 REAL, s2 REAL, s3 REAL,
  mean_response REAL, max_response REAL, min_response REAL,
  anomaly_score REAL, health_score REAL,
  status TEXT,                          -- NORMAL | POSSIBLE ANOMALY | URGENT REVIEW | NO BASELINE
  source TEXT NOT NULL CHECK (source IN ('live','sim','mixed')),
  samples INTEGER, duration_s REAL,
  trace_json TEXT,
  notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_impact_trials ON impact_trials(structure_id, ts_ms);

-- ---- Element Test Lab: cubes, beams, slabs, columns tested per IS-code procedures (simulated or manually entered) ----
CREATE TABLE IF NOT EXISTS element_tests (
  id TEXT PRIMARY KEY,
  ts_ms INTEGER NOT NULL,
  element_type TEXT NOT NULL CHECK (element_type IN ('cube','beam','slab','column')),
  procedure TEXT NOT NULL,
  label TEXT,
  grade TEXT NOT NULL,
  fck REAL NOT NULL,
  params_json TEXT NOT NULL,
  source TEXT NOT NULL CHECK (source IN ('sim','manual')),
  defect REAL,                          -- simulated defect level 0..1 (NULL for manual entries)
  metrics_json TEXT NOT NULL,           -- the raw per-channel numbers used for the checks
  channels_json TEXT NOT NULL,          -- per-channel results: checks, status, score, series
  verdict TEXT,                         -- PASS | REVIEW | FAIL | INCOMPLETE
  index_score REAL,                     -- 0-100 from the ACTIVE channels only
  image_file TEXT, overlay_file TEXT,
  notes TEXT,
  user_name TEXT
);
CREATE INDEX IF NOT EXISTS idx_element_tests ON element_tests(element_type, ts_ms);
