"""EvolutionTracker - Track code evolution timeline."""

from typing import Optional


class EvolutionTracker:
    def __init__(self, db):
        self.db = db

    def record_change(self, symbol_name: str, change_type: str, old_value: str, new_value: str):
        symbol = self.db.query('SELECT id FROM symbols WHERE name = ? ORDER BY created_at DESC LIMIT 1', (symbol_name,))
        if not symbol:
            return
        symbol_id = symbol[0]['id']
        latest = self.db.query('SELECT MAX(version) as max_ver FROM evolution_history WHERE symbol_id = ?', (symbol_id,))[0]['max_ver'] or 0
        self.db.execute('INSERT INTO evolution_history (symbol_id, version, change_type, old_value, new_value) VALUES (?, ?, ?, ?, ?)', (symbol_id, latest + 1, change_type, old_value[:500], new_value[:500]))

    def get_evolution(self, symbol_name: str) -> list:
        symbol = self.db.query('SELECT id FROM symbols WHERE name = ?', (symbol_name,))
        if not symbol:
            return []
        return self.db.query('SELECT version, change_type, old_value, new_value, timestamp FROM evolution_history WHERE symbol_id = ? ORDER BY version', (symbol[0]['id'],))

    def get_change_frequency(self, symbol_name: str) -> dict:
        symbol = self.db.query('SELECT id FROM symbols WHERE name = ?', (symbol_name,))
        if not symbol:
            return {'total_versions': 0, 'change_types': {}}
        total = self.db.query('SELECT COUNT(*) as count FROM evolution_history WHERE symbol_id = ?', (symbol[0]['id'],))[0]['count']
        types = self.db.query('SELECT change_type, COUNT(*) as count FROM evolution_history WHERE symbol_id = ? GROUP BY change_type', (symbol[0]['id'],))
        return {'total_versions': total, 'change_types': {row['change_type']: row['count'] for row in types}}