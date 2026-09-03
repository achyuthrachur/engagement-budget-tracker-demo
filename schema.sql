PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
  version      INTEGER PRIMARY KEY,
  applied_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS engagements (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  engagement_code   TEXT NOT NULL UNIQUE,
  client_name       TEXT NOT NULL,
  engagement_type   TEXT,
  complexity_mode   TEXT NOT NULL DEFAULT 'simple'
                    CHECK (complexity_mode IN ('simple', 'complex')),
  model_type        TEXT,
  model_vendor      TEXT,
  engagement_lead   TEXT,
  first_monday      TEXT,
  duration_weeks    INTEGER DEFAULT 1 CHECK (duration_weeks IS NULL OR duration_weeks > 0),
  status            TEXT NOT NULL DEFAULT 'planning'
                    CHECK (status IN ('planning', 'active', 'closed')),
  rate_mode         TEXT NOT NULL DEFAULT 'governed'
                    CHECK (rate_mode IN ('governed', 'custom', 'flat_tiered')),
  flat_tier_notes   TEXT,
  c360_used         INTEGER DEFAULT 0 CHECK (c360_used IN (0, 1)),
  c360_amount       REAL DEFAULT 0,
  bima_amount       REAL DEFAULT 0,
  created_at        TEXT,
  updated_at        TEXT
);

CREATE TABLE IF NOT EXISTS phases (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  engagement_id     INTEGER NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
  phase_name        TEXT NOT NULL,
  phase_code        TEXT,
  sow_fees          REAL DEFAULT 0,
  sort_order        INTEGER DEFAULT 0,
  is_default        INTEGER DEFAULT 0 CHECK (is_default IN (0, 1)),
  created_at        TEXT,
  UNIQUE (engagement_id, phase_name)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_phases_code_unique
  ON phases(engagement_id, phase_code COLLATE NOCASE)
  WHERE phase_code IS NOT NULL AND TRIM(phase_code) != '';

CREATE TABLE IF NOT EXISTS team_members (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  engagement_id     INTEGER NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
  name              TEXT NOT NULL,
  role              TEXT,
  is_offshore       INTEGER DEFAULT 0 CHECK (is_offshore IN (0, 1)),
  is_active         INTEGER DEFAULT 1 CHECK (is_active IN (0, 1)),
  internal_rate     REAL DEFAULT 0,
  engagement_rate   REAL DEFAULT 0,
  contract_rate     REAL DEFAULT 0,
  dte_rate          REAL DEFAULT 0,
  rate_tier_id      INTEGER REFERENCES engagement_rate_tiers(id) ON DELETE SET NULL,
  is_custom_rate    INTEGER DEFAULT 0 CHECK (is_custom_rate IN (0, 1)),
  custom_rate_note  TEXT,
  created_at        TEXT,
  UNIQUE (engagement_id, name COLLATE NOCASE)
);

CREATE TABLE IF NOT EXISTS phase_person_weeks (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  phase_id          INTEGER NOT NULL REFERENCES phases(id) ON DELETE CASCADE,
  team_member_id    INTEGER NOT NULL REFERENCES team_members(id) ON DELETE CASCADE,
  week_start_date   TEXT,
  budgeted_hours    REAL DEFAULT 0,
  forecasted_hours  REAL,
  UNIQUE (phase_id, team_member_id, week_start_date)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ppw_simple_unique
  ON phase_person_weeks(phase_id, team_member_id)
  WHERE week_start_date IS NULL;
CREATE INDEX IF NOT EXISTS idx_ppw_phase_week
  ON phase_person_weeks(phase_id, week_start_date);
CREATE INDEX IF NOT EXISTS idx_ppw_member
  ON phase_person_weeks(team_member_id);

CREATE TABLE IF NOT EXISTS budget_adjustments (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  engagement_id     INTEGER NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
  phase_id          INTEGER REFERENCES phases(id) ON DELETE RESTRICT,
  adjustment_type   TEXT NOT NULL
                    CHECK (adjustment_type IN ('markdown', 'c360', 'bima', 'change_order')),
  effective_date    TEXT,
  amount            REAL DEFAULT 0,
  description       TEXT,
  created_at        TEXT,
  CHECK (adjustment_type != 'change_order' OR phase_id IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_adjustments_engagement
  ON budget_adjustments(engagement_id, phase_id, adjustment_type);

CREATE TABLE IF NOT EXISTS budget_revisions (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  engagement_id         INTEGER NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
  phase_id              INTEGER REFERENCES phases(id) ON DELETE SET NULL,
  team_member_id        INTEGER REFERENCES team_members(id) ON DELETE SET NULL,
  phase_person_week_id  INTEGER REFERENCES phase_person_weeks(id) ON DELETE SET NULL,
  field_name            TEXT NOT NULL,
  old_value             REAL,
  new_value             REAL,
  reason                TEXT NOT NULL CHECK (TRIM(reason) != ''),
  revised_at            TEXT
);
CREATE INDEX IF NOT EXISTS idx_revisions_engagement
  ON budget_revisions(engagement_id, revised_at DESC);

CREATE TABLE IF NOT EXISTS expenses (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  engagement_id     INTEGER NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
  phase_id          INTEGER REFERENCES phases(id) ON DELETE RESTRICT,
  expense_type      TEXT NOT NULL CHECK (expense_type IN ('crowe_paid', 'client_paid')),
  description       TEXT,
  amount            REAL DEFAULT 0,
  incurred_date     TEXT,
  created_at        TEXT
);
CREATE INDEX IF NOT EXISTS idx_expenses_engagement
  ON expenses(engagement_id, phase_id, expense_type);

CREATE TABLE IF NOT EXISTS weekly_snapshots (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  engagement_id     INTEGER NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
  week_end_date     TEXT NOT NULL,
  imported_at       TEXT,
  row_count         INTEGER,
  notes             TEXT,
  covered_start_date TEXT,
  covered_end_date   TEXT,
  realization_value  REAL,
  realization_delta  REAL,
  rows_inserted      INTEGER DEFAULT 0,
  rows_updated       INTEGER DEFAULT 0,
  rows_removed       INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_weekly_snapshots_engagement
  ON weekly_snapshots(engagement_id, week_end_date);

CREATE TABLE IF NOT EXISTS time_entries (
  id                   INTEGER PRIMARY KEY AUTOINCREMENT,
  snapshot_id          INTEGER NOT NULL REFERENCES weekly_snapshots(id) ON DELETE CASCADE,
  engagement_id        INTEGER NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
  transaction_id       TEXT UNIQUE,
  worker_name          TEXT,
  worker_id            TEXT,
  title                TEXT,
  worker_bu_du_cc      TEXT,
  competency_center    TEXT,
  entry_date           TEXT,
  week_end_date        TEXT,
  financial_period     TEXT,
  project_id           TEXT,
  project_name         TEXT,
  xref                 TEXT,
  phase_desc           TEXT,
  task_desc            TEXT,
  work_location        TEXT,
  billing_status       TEXT,
  hours                REAL DEFAULT 0,
  fees_std_rate        REAL DEFAULT 0,
  fees_contract_rate   REAL DEFAULT 0,
  memo                 TEXT,
  normalized_worker_name TEXT,
  is_excluded          INTEGER DEFAULT 0 CHECK (is_excluded IN (0, 1)),
  exclusion_reason     TEXT,
  matched_team_member_id INTEGER REFERENCES team_members(id) ON DELETE SET NULL,
  matched_phase_id     INTEGER REFERENCES phases(id) ON DELETE SET NULL,
  allocation_method    TEXT
);
CREATE INDEX IF NOT EXISTS idx_time_entries_engagement
  ON time_entries(engagement_id);
CREATE INDEX IF NOT EXISTS idx_time_entries_snapshot
  ON time_entries(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_time_entries_worker
  ON time_entries(engagement_id, worker_name, week_end_date);
CREATE INDEX IF NOT EXISTS idx_time_entries_phase
  ON time_entries(engagement_id, matched_phase_id, week_end_date);

CREATE TABLE IF NOT EXISTS settings (
  key   TEXT PRIMARY KEY,
  value TEXT
);

CREATE TABLE IF NOT EXISTS engagement_events (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  engagement_id     INTEGER NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
  event_type        TEXT NOT NULL,
  description       TEXT NOT NULL,
  created_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_engagement_events
  ON engagement_events(engagement_id, created_at DESC);

CREATE TABLE IF NOT EXISTS proposals (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  proposal_code     TEXT NOT NULL UNIQUE,
  client_name       TEXT NOT NULL,
  engagement_type   TEXT,
  first_monday      TEXT,
  duration_weeks    INTEGER DEFAULT 1 CHECK (duration_weeks IS NULL OR duration_weeks > 0),
  rate_basis        TEXT NOT NULL DEFAULT 'standard'
                    CHECK (rate_basis IN ('standard','engagement','contract')),
  discount_rate     REAL NOT NULL DEFAULT 0 CHECK (discount_rate BETWEEN 0 AND 1),
  status            TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','converted','archived')),
  converted_engagement_id INTEGER REFERENCES engagements(id) ON DELETE SET NULL,
  notes             TEXT,
  created_at        TEXT,
  updated_at        TEXT
);

CREATE TABLE IF NOT EXISTS proposal_people (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  proposal_id       INTEGER NOT NULL REFERENCES proposals(id) ON DELETE CASCADE,
  name              TEXT,
  role              TEXT,
  base_rate         REAL,
  discount_rate     REAL NOT NULL DEFAULT 0 CHECK (discount_rate BETWEEN 0 AND 1),
  rough_rate        REAL,
  created_at        TEXT
);

CREATE TABLE IF NOT EXISTS proposal_person_weeks (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  proposal_person_id INTEGER NOT NULL REFERENCES proposal_people(id) ON DELETE CASCADE,
  week_start_date    TEXT,
  budgeted_hours     REAL DEFAULT 0,
  forecasted_hours   REAL
);

CREATE TABLE IF NOT EXISTS rate_cards (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  name              TEXT NOT NULL UNIQUE,
  is_active         INTEGER DEFAULT 1 CHECK (is_active IN (0,1)),
  created_at        TEXT
);

CREATE TABLE IF NOT EXISTS rate_card_rates (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  rate_card_id      INTEGER NOT NULL REFERENCES rate_cards(id) ON DELETE CASCADE,
  role_name         TEXT NOT NULL,
  standard_rate     REAL DEFAULT 0,
  engagement_rate   REAL DEFAULT 0,
  contract_rate     REAL DEFAULT 0,
  dte_rate          REAL DEFAULT 0,
  locked_at         TEXT,
  UNIQUE (rate_card_id, role_name COLLATE NOCASE)
);

CREATE TABLE IF NOT EXISTS engagement_rate_tiers (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  engagement_id     INTEGER NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
  tier_name         TEXT NOT NULL,
  tier_amount       REAL DEFAULT 0,
  tier_order        INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS import_exceptions (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  engagement_id       INTEGER NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
  transaction_id      TEXT,
  worker_name         TEXT,
  normalized_worker_name TEXT,
  phase_desc          TEXT,
  exception_code      TEXT NOT NULL,
  status              TEXT NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending', 'resolved', 'excluded')),
  hours               REAL DEFAULT 0,
  fees_contract_rate  REAL DEFAULT 0,
  snapshot_id         INTEGER REFERENCES weekly_snapshots(id) ON DELETE SET NULL,
  time_entry_id       INTEGER REFERENCES time_entries(id) ON DELETE CASCADE,
  resolution_note     TEXT,
  created_at          TEXT,
  updated_at          TEXT
);
CREATE INDEX IF NOT EXISTS idx_import_exceptions_engagement
  ON import_exceptions(engagement_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_import_exceptions_entry_code
  ON import_exceptions(time_entry_id, exception_code)
  WHERE time_entry_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS allocation_rules (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  engagement_id     INTEGER NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
  team_member_id    INTEGER NOT NULL REFERENCES team_members(id) ON DELETE CASCADE,
  phase_id          INTEGER NOT NULL REFERENCES phases(id) ON DELETE CASCADE,
  created_at        TEXT,
  created_from_exception_id INTEGER REFERENCES import_exceptions(id) ON DELETE SET NULL,
  UNIQUE (engagement_id, team_member_id, phase_id)
);

CREATE TABLE IF NOT EXISTS engagement_drafts (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  engagement_code   TEXT,
  client_name       TEXT,
  step              INTEGER NOT NULL DEFAULT 1,
  wizard_json       TEXT NOT NULL,
  created_at        TEXT,
  updated_at        TEXT
);
