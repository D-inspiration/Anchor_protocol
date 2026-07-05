"""DecisionManager - Lightweight Architecture Decision Records (ADR-lite) for agent actions.

Captures the "why" behind a change: which actor made it, what reasoning drove it,
what evidence supported it, what consequences followed, and how confident the
actor was. This is the piece "Intent / Context / History" leaves out: an
explicit, queryable trail of *decisions*, not just diffs.
"""

import json
import uuid
from typing import Dict, Any, List, Optional


class DecisionManager:
    def __init__(self, db):
        self.db = db

    def record_decision(self, actor: str, reason: str, evidence: Optional[List[str]] = None,
                         consequences: Optional[List[str]] = None, confidence: float = 1.0,
                         symbol_name: Optional[str] = None, file_path: Optional[str] = None) -> str:
        """Record a decision. Returns a decision id like 'DEC-0001'."""
        if not (0.0 <= confidence <= 1.0):
            raise ValueError("confidence must be between 0.0 and 1.0")

        symbol_id = None
        if symbol_name:
            symbol = self.db.query(
                'SELECT id FROM symbols WHERE name = ? ORDER BY created_at DESC LIMIT 1', (symbol_name,)
            )
            if symbol:
                symbol_id = symbol[0]['id']

        count = self.db.query('SELECT COUNT(*) as c FROM decisions')[0]['c']
        decision_id = f"DEC-{count + 1:04d}"
        # Guard against id collision (e.g. after a reset/replay scenario)
        while self.db.query('SELECT id FROM decisions WHERE id = ?', (decision_id,)):
            count += 1
            decision_id = f"DEC-{count + 1:04d}"

        self.db.execute(
            'INSERT INTO decisions (id, actor, reason, evidence, consequences, confidence, symbol_id, file_path) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (decision_id, actor, reason, json.dumps(evidence or []), json.dumps(consequences or []),
             confidence, symbol_id, file_path)
        )
        return decision_id

    def get_decision(self, decision_id: str) -> Optional[Dict[str, Any]]:
        rows = self.db.query('SELECT * FROM decisions WHERE id = ?', (decision_id,))
        if not rows:
            return None
        return self._hydrate(rows[0])

    def list_decisions(self, symbol_name: Optional[str] = None, actor: Optional[str] = None,
                        limit: int = 50) -> List[Dict[str, Any]]:
        if symbol_name:
            rows = self.db.query('''
                SELECT d.* FROM decisions d
                JOIN symbols s ON d.symbol_id = s.id
                WHERE s.name = ?
                ORDER BY d.created_at DESC LIMIT ?
            ''', (symbol_name, limit))
        elif actor:
            rows = self.db.query(
                'SELECT * FROM decisions WHERE actor = ? ORDER BY created_at DESC LIMIT ?', (actor, limit)
            )
        else:
            rows = self.db.query('SELECT * FROM decisions ORDER BY created_at DESC LIMIT ?', (limit,))
        return [self._hydrate(r) for r in rows]

    def low_confidence_high_impact(self, confidence_threshold: float = 0.6) -> List[Dict[str, Any]]:
        """
        Decisions that should probably have required human approval:
        low confidence + touched a symbol with existing drift/impact history.
        """
        rows = self.db.query('''
            SELECT d.*, COUNT(ci.id) as impact_count
            FROM decisions d
            LEFT JOIN change_impacts ci ON ci.edited_symbol_id = d.symbol_id AND ci.breakage_detected = 1
            WHERE d.confidence <= ?
            GROUP BY d.id
            HAVING impact_count > 0
            ORDER BY d.created_at DESC
        ''', (confidence_threshold,))
        return [self._hydrate(r) for r in rows]

    def requires_human_approval(self, confidence: float, blast_radius_risk: str,
                                 confidence_threshold: float = 0.6) -> bool:
        """Policy: low confidence + high blast radius risk => human-in-the-loop."""
        return confidence <= confidence_threshold and blast_radius_risk in ('HIGH', 'CRITICAL')

    def _hydrate(self, row: Dict[str, Any]) -> Dict[str, Any]:
        d = dict(row)
        d['evidence'] = json.loads(d['evidence']) if d.get('evidence') else []
        d['consequences'] = json.loads(d['consequences']) if d.get('consequences') else []
        return d
