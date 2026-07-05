"""Migration runner - versioned .sql files, no ORM."""

import os
import sqlite3
from typing import List


class MigrationRunner:
    def __init__(self, db_path: str, migrations_dir: str = None):
        self.db_path = db_path
        if migrations_dir is None:
            migrations_dir = os.path.join(os.path.dirname(__file__), '..', 'migrations')
        self.migrations_dir = os.path.abspath(migrations_dir)
        os.makedirs(self.migrations_dir, exist_ok=True)

    def _ensure_migrations_table(self, conn: sqlite3.Connection):
        conn.execute('''
            CREATE TABLE IF NOT EXISTS _migrations (
                id INTEGER PRIMARY KEY,
                filename TEXT UNIQUE,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

    def get_applied(self) -> List[str]:
        conn = sqlite3.connect(self.db_path)
        self._ensure_migrations_table(conn)
        cursor = conn.execute('SELECT filename FROM _migrations ORDER BY id')
        applied = [row[0] for row in cursor.fetchall()]
        conn.close()
        return applied

    def get_pending(self) -> List[str]:
        applied = set(self.get_applied())
        all_files = sorted([f for f in os.listdir(self.migrations_dir) if f.endswith('.sql')])
        return [f for f in all_files if f not in applied]

    def run_all(self):
        pending = self.get_pending()
        if not pending:
            return 0
        conn = sqlite3.connect(self.db_path)
        self._ensure_migrations_table(conn)
        count = 0
        for filename in pending:
            filepath = os.path.join(self.migrations_dir, filename)
            with open(filepath, 'r') as f:
                sql = f.read()
            conn.executescript(sql)
            conn.execute('INSERT INTO _migrations (filename) VALUES (?)', (filename,))
            count += 1
        conn.commit()
        conn.close()
        return count

    def create_migration(self, name: str) -> str:
        """Create a new migration file with timestamp prefix."""
        import datetime
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'{ts}_{name}.sql'
        filepath = os.path.join(self.migrations_dir, filename)
        with open(filepath, 'w') as f:
            f.write(f'-- Migration: {name}\n-- Created: {ts}\n\n')
        return filepath