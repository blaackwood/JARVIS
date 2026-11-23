CREATE TABLE IF NOT EXISTS dav_changes (
  sequence INTEGER PRIMARY KEY,
  reminder_id TEXT NOT NULL,
  status TEXT NOT NULL,
  changed_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dav_changes_sequence
  ON dav_changes(sequence);
