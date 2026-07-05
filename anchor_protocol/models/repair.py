"""RepairTracker - Track AI repair loops and stabilization attempts."""

from typing import Optional


class RepairTracker:
    def __init__(self, db):
        self.db = db

    def record_attempt(self, symbol_name: Optional[str], error_type: str, error_message: str):
        if not symbol_name:
            return
        symbol = self.db.query('SELECT id FROM symbols WHERE name = ? ORDER BY created_at DESC LIMIT 1', (symbol_name,))
        if not symbol:
            return
        symbol_id = symbol[0]['id']
        attempts = self.db.query('SELECT COUNT(*) as count FROM repair_loops WHERE symbol_id = ?', (symbol_id,))[0]['count']
        self.db.execute('INSERT INTO repair_loops (symbol_id, attempt_number, error_type, error_message) VALUES (?, ?, ?, ?)', (symbol_id, attempts + 1, error_type, error_message))

    def get_repair_stats(self, symbol_name: Optional[str] = None) -> dict:
        if symbol_name:
            symbol = self.db.query('SELECT id FROM symbols WHERE name = ?', (symbol_name,))
            if not symbol:
                return {'total_attempts': 0, 'error_types': {}}
            symbol_id = symbol[0]['id']
            total = self.db.query('SELECT COUNT(*) as count FROM repair_loops WHERE symbol_id = ?', (symbol_id,))[0]['count']
            error_types = self.db.query('SELECT error_type, COUNT(*) as count FROM repair_loops WHERE symbol_id = ? GROUP BY error_type', (symbol_id,))
            return {'total_attempts': total, 'error_types': {row['error_type']: row['count'] for row in error_types}}
        total = self.db.query('SELECT COUNT(*) as count FROM repair_loops')[0]['count']
        avg = self.db.query("SELECT AVG(attempt_count) as avg FROM (SELECT symbol_id, MAX(attempt_number) as attempt_count FROM repair_loops GROUP BY symbol_id)")[0]['avg'] or 0
        error_types = self.db.query('SELECT error_type, COUNT(*) as count FROM repair_loops GROUP BY error_type')
        longest = self.db.query('SELECT s.name, MAX(r.attempt_number) as max_attempts FROM repair_loops r JOIN symbols s ON r.symbol_id = s.id GROUP BY r.symbol_id ORDER BY max_attempts DESC LIMIT 1')
        return {'total_attempts': total, 'avg_iterations': round(avg, 1), 'error_types': {row['error_type']: row['count'] for row in error_types}, 'longest_loop': longest[0] if longest else None}