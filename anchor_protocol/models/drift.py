"""DriftTracker - Detect and record code drift events."""

from typing import Optional


class DriftTracker:
    def __init__(self, db):
        self.db = db

    def record_drift(self, symbol_id: Optional[int], drift_type: str, runtime_failure: bool = False, severity: str = 'high'):
        self.db.execute('INSERT INTO drift_events (symbol_id, drift_type, severity, runtime_failure) VALUES (?, ?, ?, ?)', (symbol_id, drift_type, severity, runtime_failure))
        if symbol_id:
            symbol = self.db.query('SELECT file_id FROM symbols WHERE id = ?', (symbol_id,))
            if symbol:
                file_id = symbol[0]['file_id']
                file_info = self.db.query('SELECT path FROM files WHERE id = ?', (file_id,))
                if file_info:
                    self._update_hotspot(file_info[0]['path'])

    def _update_hotspot(self, file_path: str):
        result = self.db.query('SELECT id FROM drift_hotspots WHERE file_path = ?', (file_path,))
        if result:
            self.db.execute('UPDATE drift_hotspots SET drift_event_count = drift_event_count + 1, last_drift_at = CURRENT_TIMESTAMP WHERE id = ?', (result[0]['id'],))
        else:
            self.db.execute('INSERT INTO drift_hotspots (file_path, drift_event_count, last_drift_at) VALUES (?, 1, CURRENT_TIMESTAMP)', (file_path,))

    def get_drift_summary(self, days: int = 7) -> dict:
        total = self.db.query("SELECT COUNT(*) as count FROM drift_events WHERE detected_at > datetime('now', '-{} days')".format(days))[0]['count']
        by_type = self.db.query("SELECT drift_type, COUNT(*) as count FROM drift_events WHERE detected_at > datetime('now', '-{} days') GROUP BY drift_type".format(days))
        unresolved = self.db.query("SELECT COUNT(*) as count FROM drift_events WHERE resolved_at IS NULL")[0]['count']
        return {'total_drifts': total, 'by_type': {row['drift_type']: row['count'] for row in by_type}, 'unresolved': unresolved}

    def resolve_drift(self, drift_id: int, iterations: int = 1):
        self.db.execute('UPDATE drift_events SET resolved_at = CURRENT_TIMESTAMP, recovery_iterations = ? WHERE id = ?', (iterations, drift_id))