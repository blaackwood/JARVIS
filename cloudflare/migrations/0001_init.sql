CREATE TABLE IF NOT EXISTS reminders (
  id TEXT PRIMARY KEY,
  message TEXT NOT NULL,
  due_ts REAL,
  due_raw TEXT,
  date_only INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'open',
  description TEXT NOT NULL DEFAULT '',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  completed_at INTEGER,
  cancelled_at INTEGER,
  etag TEXT NOT NULL,
  sequence INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_reminders_status_due
  ON reminders(status, due_ts);

CREATE TABLE IF NOT EXISTS dav_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

INSERT OR IGNORE INTO dav_meta(key, value) VALUES ('sync_seq', '1');
