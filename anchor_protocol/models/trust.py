"""AgentTrustManager - Per-agent contract/invariant compliance scores.

In a multi-agent world (Claude, Codex, Cursor Composer, local models...) not
every agent earns the same trust. This tracks, per named agent, how often its
proposed edits violated contracts or invariants, so Anchor can eventually
answer "which agent should touch the payment pipeline".
"""

from typing import Dict, Any, List, Optional


class AgentTrustManager:
    def __init__(self, db):
        self.db = db

    def _ensure_row(self, agent_name: str):
        existing = self.db.query('SELECT agent_name FROM agent_trust WHERE agent_name = ?', (agent_name,))
        if not existing:
            self.db.execute('INSERT INTO agent_trust (agent_name) VALUES (?)', (agent_name,))

    def record_operation(self, agent_name: str, contract_compliant: bool = True,
                          invariant_compliant: bool = True) -> None:
        self._ensure_row(agent_name)
        self.db.execute('''
            UPDATE agent_trust SET
                total_ops = total_ops + 1,
                compliant_ops = compliant_ops + ?,
                contract_violations = contract_violations + ?,
                invariant_violations = invariant_violations + ?,
                last_active = CURRENT_TIMESTAMP
            WHERE agent_name = ?
        ''', (
            1 if (contract_compliant and invariant_compliant) else 0,
            0 if contract_compliant else 1,
            0 if invariant_compliant else 1,
            agent_name,
        ))

    def get_trust_score(self, agent_name: str) -> Dict[str, Any]:
        row = self.db.query('SELECT * FROM agent_trust WHERE agent_name = ?', (agent_name,))
        if not row:
            return {'agent_name': agent_name, 'total_ops': 0, 'compliance_rate': None}
        r = row[0]
        rate = (r['compliant_ops'] / r['total_ops']) if r['total_ops'] else None
        return {
            'agent_name': agent_name,
            'total_ops': r['total_ops'],
            'compliant_ops': r['compliant_ops'],
            'contract_violations': r['contract_violations'],
            'invariant_violations': r['invariant_violations'],
            'compliance_rate': round(rate, 3) if rate is not None else None,
            'last_active': r['last_active'],
        }

    def leaderboard(self, min_ops: int = 1) -> List[Dict[str, Any]]:
        """Agents ranked by compliance rate, for 'preferred agent for X' decisions."""
        rows = self.db.query('SELECT * FROM agent_trust WHERE total_ops >= ? ORDER BY agent_name', (min_ops,))
        scored = []
        for r in rows:
            rate = r['compliant_ops'] / r['total_ops'] if r['total_ops'] else 0.0
            scored.append({
                'agent_name': r['agent_name'],
                'total_ops': r['total_ops'],
                'compliance_rate': round(rate, 3),
                'contract_violations': r['contract_violations'],
                'invariant_violations': r['invariant_violations'],
            })
        scored.sort(key=lambda x: x['compliance_rate'], reverse=True)
        return scored

    def preferred_agent(self, min_ops: int = 3) -> Optional[str]:
        board = self.leaderboard(min_ops=min_ops)
        return board[0]['agent_name'] if board else None
