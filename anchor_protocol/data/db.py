"""Database - SQLite persistence with query builder integration."""

import os
import sqlite3
from typing import Optional, List, Dict, Any
from .query import Q
from .migrations import MigrationRunner


class Database:
    def __init__(self, project_root: str):
        # NOTE: project_root here must be the *project* root, not a db file path.
        # (Previously AnchorSidecar passed the full db path in, which caused a
        # double-nested '.anchor/anchor.db/.anchor/anchor.db' path. Fixed at the
        # call site in sidecar.py -- keep this constructor accepting project_root.)
        self.project_root = project_root
        self.db_path = os.path.join(project_root, '.anchor', 'anchor.db')
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.migrations = MigrationRunner(self.db_path)

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_schema(self):
        """Run migrations and ensure base schema exists."""
        ran = self.migrations.run_all()
        
        conn = self._connect()
        cursor = conn.cursor()
    
        tables = [
            # NEW: Tiered session scope
            'CREATE TABLE IF NOT EXISTS sessions (session_id TEXT PRIMARY KEY, project_root TEXT NOT NULL, context_files TEXT DEFAULT \'[]\', active_files TEXT DEFAULT \'[]\', frozen_files TEXT DEFAULT \'[]\', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)',
            'CREATE TABLE IF NOT EXISTS files (id INTEGER PRIMARY KEY, path TEXT UNIQUE, last_hash TEXT, last_seen TIMESTAMP)',
            'CREATE TABLE IF NOT EXISTS symbols (id INTEGER PRIMARY KEY, file_id INTEGER, name TEXT, symbol_type TEXT, start_line INTEGER, end_line INTEGER, signature TEXT, return_annotation TEXT, arguments TEXT, complexity_score REAL, dependency_density REAL, created_at TIMESTAMP, FOREIGN KEY (file_id) REFERENCES files(id))',
            'CREATE TABLE IF NOT EXISTS contracts (id INTEGER PRIMARY KEY, symbol_id INTEGER, contract_type TEXT, contract_value TEXT, confidence REAL, FOREIGN KEY (symbol_id) REFERENCES symbols(id))',
            'CREATE TABLE IF NOT EXISTS dependencies (id INTEGER PRIMARY KEY, symbol_id INTEGER, depends_on_symbol_id INTEGER, dependency_type TEXT, FOREIGN KEY (symbol_id) REFERENCES symbols(id), FOREIGN KEY (depends_on_symbol_id) REFERENCES symbols(id))',
            'CREATE TABLE IF NOT EXISTS operations (id INTEGER PRIMARY KEY, session_id TEXT, operation TEXT, path TEXT, hash TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)',
            'CREATE TABLE IF NOT EXISTS proposals (ticket_id TEXT PRIMARY KEY, session_id TEXT, path TEXT, old_content TEXT, new_content TEXT, reason TEXT, symbol_name TEXT, change_type TEXT, actor TEXT DEFAULT \'unknown\', confidence REAL DEFAULT 1.0, status TEXT DEFAULT pending, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)',
            'CREATE TABLE IF NOT EXISTS drift_events (id INTEGER PRIMARY KEY, symbol_id INTEGER, drift_type TEXT, severity TEXT, detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, runtime_failure BOOLEAN, recovery_iterations INTEGER DEFAULT 0, resolved_at TIMESTAMP, FOREIGN KEY (symbol_id) REFERENCES symbols(id))',
            'CREATE TABLE IF NOT EXISTS change_impacts (id INTEGER PRIMARY KEY, change_id TEXT, edited_symbol_id INTEGER, affected_symbol_id INTEGER, breakage_detected BOOLEAN, fix_iterations INTEGER DEFAULT 0, FOREIGN KEY (edited_symbol_id) REFERENCES symbols(id), FOREIGN KEY (affected_symbol_id) REFERENCES symbols(id))',
            'CREATE TABLE IF NOT EXISTS repair_loops (id INTEGER PRIMARY KEY, symbol_id INTEGER, attempt_number INTEGER, error_type TEXT, error_message TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (symbol_id) REFERENCES symbols(id))',
            'CREATE TABLE IF NOT EXISTS evolution_history (id INTEGER PRIMARY KEY, symbol_id INTEGER, version INTEGER, change_type TEXT, old_value TEXT, new_value TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (symbol_id) REFERENCES symbols(id))',
            'CREATE TABLE IF NOT EXISTS drift_hotspots (id INTEGER PRIMARY KEY, file_path TEXT, drift_event_count INTEGER DEFAULT 0, last_drift_at TIMESTAMP)',
            'CREATE TABLE IF NOT EXISTS io_contracts (id INTEGER PRIMARY KEY, symbol_id INTEGER, inputs TEXT, output_type TEXT, side_effects TEXT, confidence REAL, declared_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (symbol_id) REFERENCES symbols(id))',
            'CREATE TABLE IF NOT EXISTS execution_traces (id INTEGER PRIMARY KEY, call_id TEXT, symbol_id INTEGER, inputs TEXT, output TEXT, execution_time_ms REAL, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (symbol_id) REFERENCES symbols(id))',
            # Governance layer: decisions, assumptions, invariants, agent trust
            'CREATE TABLE IF NOT EXISTS decisions (id TEXT PRIMARY KEY, actor TEXT, reason TEXT, evidence TEXT, consequences TEXT, confidence REAL DEFAULT 1.0, symbol_id INTEGER, file_path TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (symbol_id) REFERENCES symbols(id))',
            'CREATE TABLE IF NOT EXISTS assumptions (id INTEGER PRIMARY KEY, symbol_id INTEGER, text TEXT, source TEXT DEFAULT \'manual\', status TEXT DEFAULT \'active\', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, violated_at TIMESTAMP, violation_evidence TEXT, FOREIGN KEY (symbol_id) REFERENCES symbols(id))',
            'CREATE TABLE IF NOT EXISTS invariants (id INTEGER PRIMARY KEY, name TEXT UNIQUE, description TEXT, scope TEXT, severity TEXT DEFAULT \'high\', check_expr TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)',
            'CREATE TABLE IF NOT EXISTS invariant_violations (id INTEGER PRIMARY KEY, invariant_id INTEGER, path TEXT, detail TEXT, detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (invariant_id) REFERENCES invariants(id))',
            'CREATE TABLE IF NOT EXISTS agent_trust (agent_name TEXT PRIMARY KEY, total_ops INTEGER DEFAULT 0, compliant_ops INTEGER DEFAULT 0, contract_violations INTEGER DEFAULT 0, invariant_violations INTEGER DEFAULT 0, last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP)',
            # Incident records (case studies -- "what broke, why, how it was caught")
            'CREATE TABLE IF NOT EXISTS incidents (id INTEGER PRIMARY KEY, name TEXT, cause TEXT, impact TEXT, detection TEXT, severity TEXT DEFAULT \'medium\', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)',
            # Local, opt-in telemetry queue (never sent anywhere unless the user explicitly exports/enables it)
            'CREATE TABLE IF NOT EXISTS telemetry_events (id INTEGER PRIMARY KEY, event_type TEXT, payload TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)',
        ]
    
        for sql in tables:
            cursor.execute(sql)
    
        conn.commit()
        conn.close()
        return ran
    
    def log_operation(self, session_id: str, operation: str, path: str, hash_val: str):
        self.execute(
            'INSERT INTO operations (session_id, operation, path, hash) VALUES (?, ?, ?, ?)',
            (session_id, operation, path, hash_val)
        )

    def store_proposal(self, ticket_id: str, session_id: str, proposal):
        self.execute(
            'INSERT INTO proposals (ticket_id, session_id, path, old_content, new_content, reason, symbol_name, change_type, actor, confidence) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (ticket_id, session_id, proposal.path, proposal.old_content, proposal.new_content,
             proposal.reason, proposal.symbol_name, proposal.change_type,
             getattr(proposal, 'actor', 'unknown'), getattr(proposal, 'confidence', 1.0))
        )

    def get_proposal(self, ticket_id: str) -> Optional[Any]:
        row = self.query_one('SELECT * FROM proposals WHERE ticket_id = ?', (ticket_id,))
        if row:
            from ..sidecar import EditProposal
            return EditProposal(path=row['path'], old_content=row['old_content'], new_content=row['new_content'],
                              reason=row['reason'], symbol_name=row['symbol_name'], change_type=row['change_type'],
                              actor=row['actor'], confidence=row['confidence']), row['created_at']
        return None

    def query(self, sql: str, params: tuple = ()) -> List[Dict]:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(sql, params)
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def execute(self, sql: str, params: tuple = ()):
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(sql, params)
        conn.commit()
        lastrowid = cursor.lastrowid
        conn.close()
        return lastrowid

    def query_one(self, sql: str, params: tuple = ()) -> Optional[Dict]:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def commit(self):
        conn = self._connect()
        conn.commit()
        conn.close()
        