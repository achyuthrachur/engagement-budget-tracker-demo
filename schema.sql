PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS engagements (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  engagement_code    TEXT NOT NULL UNIQUE,
  client_name        TEXT NOT NULL,
  model_type         TEXT,
  model_vendor       TEXT,
  engagement_lead    TEXT,
  first_week_with_entry TEXT,
  max_sow_fees       REAL DEFAULT 0,
  change_order_amt   REAL DEFAULT 0,
  c360_used          INTEGER DEFAULT 0,
  c360_amount        REAL DEFAULT 0,
  bima_amount        REAL DEFAULT 0,
  status             TEXT DEFAULT 'Active',
  created_at         TEXT,
  updated_at         TEXT
);

CREATE TABLE IF NOT EXISTS team_members (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  engagement_id      INTEGER REFERENCES engagements(id) ON DELETE CASCADE,
  name               TEXT NOT NULL,
  role               TEXT,
  internal_rate      REAL DEFAULT 0,
  engagement_rate    REAL DEFAULT 0,
  budgeted_hours     REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS phases (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  engagement_id      INTEGER REFERENCES engagements(id) ON DELETE CASCADE,
  phase_name         TEXT NOT NULL,
  budgeted_hours     REAL DEFAULT 0,
  budgeted_eng_fees  REAL DEFAULT 0,
  sort_order         INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS weekly_snapshots (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  engagement_id      INTEGER REFERENCES engagements(id) ON DELETE CASCADE,
  week_end_date      TEXT NOT NULL,
  imported_at        TEXT,
  row_count          INTEGER,
  notes              TEXT
);

CREATE TABLE IF NOT EXISTS time_entries (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  snapshot_id        INTEGER REFERENCES weekly_snapshots(id) ON DELETE CASCADE,
  engagement_id      INTEGER REFERENCES engagements(id) ON DELETE CASCADE,
  transaction_id     TEXT UNIQUE,
  worker_name        TEXT,
  worker_id          TEXT,
  title              TEXT,
  entry_date         TEXT,
  week_end_date      TEXT,
  financial_period   TEXT,
  phase_desc         TEXT,
  task_desc          TEXT,
  work_location      TEXT,
  billing_status     TEXT,
  hours              REAL DEFAULT 0,
  fees_std_rate      REAL DEFAULT 0,
  fees_contract_rate REAL DEFAULT 0,
  memo               TEXT
);

CREATE INDEX IF NOT EXISTS idx_time_entries_engagement ON time_entries(engagement_id);
CREATE INDEX IF NOT EXISTS idx_time_entries_snapshot ON time_entries(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_time_entries_worker ON time_entries(engagement_id, worker_name);
CREATE INDEX IF NOT EXISTS idx_weekly_snapshots_engagement ON weekly_snapshots(engagement_id);

CREATE TABLE IF NOT EXISTS budget_adjustments (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  engagement_id      INTEGER REFERENCES engagements(id) ON DELETE CASCADE,
  effective_date     TEXT,
  adjustment_type    TEXT,
  amount             REAL DEFAULT 0,
  description        TEXT,
  created_at         TEXT
);

CREATE TABLE IF NOT EXISTS settings (
  key                TEXT PRIMARY KEY,
  value              TEXT
);
