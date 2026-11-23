CREATE TABLE IF NOT EXISTS calendars (
  calendar_id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  created_at INTEGER NOT NULL
);

INSERT OR IGNORE INTO calendars (calendar_id, display_name, created_at)
VALUES ('JARVIS', 'JARVIS', CAST(strftime('%s','now') AS INTEGER));

ALTER TABLE reminders ADD COLUMN calendar_id TEXT NOT NULL DEFAULT 'JARVIS';

CREATE INDEX IF NOT EXISTS idx_reminders_calendar_status_due
  ON reminders(calendar_id, status, due_ts);
