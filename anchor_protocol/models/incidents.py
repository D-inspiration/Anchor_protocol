"""IncidentManager - Post-mortems as structured, queryable data.

Anchor's own history is the first dataset: when a bug slips through (or gets
caught), record it as a structured incident instead of a paragraph in a
commit message. Over time this becomes the same kind of "which failure modes
recur" data the telemetry layer collects across many projects.
"""

from typing import Dict, Any, List, Optional


class IncidentManager:
    def __init__(self, db):
        self.db = db

    def record_incident(self, name: str, cause: str, impact: str, detection: str,
                         severity: str = 'medium') -> int:
        return self.db.execute(
            'INSERT INTO incidents (name, cause, impact, detection, severity) VALUES (?, ?, ?, ?, ?)',
            (name, cause, impact, detection, severity)
        )

    def list_incidents(self, severity: Optional[str] = None) -> List[Dict[str, Any]]:
        if severity:
            return self.db.query('SELECT * FROM incidents WHERE severity = ? ORDER BY created_at DESC', (severity,))
        return self.db.query('SELECT * FROM incidents ORDER BY created_at DESC')

    def get_incident(self, incident_id: int) -> Optional[Dict[str, Any]]:
        rows = self.db.query('SELECT * FROM incidents WHERE id = ?', (incident_id,))
        return rows[0] if rows else None
