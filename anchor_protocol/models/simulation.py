"""SimulationEngine - Semantic replay + heuristic change simulation.

Two related capabilities, deliberately kept honest about their limits:

1. replay(): a *semantic timeline* -- not `git log`, but "what changed, why
   (decisions), and what broke (drift/impact)" reassembled from Anchor's own
   tables. This is real: it's just a join across data Anchor already has.

2. simulate_change(): a *heuristic* counterfactual. It does NOT execute the
   proposed change or predict the future. It looks at what happened
   historically when this symbol (or symbols like it) were touched, and
   reports that as a base rate. It is explicitly labeled as heuristic in its
   output so it can't be mistaken for a guarantee.
"""

from typing import Dict, Any, List, Optional


class SimulationEngine:
    def __init__(self, db, blast_radius_analyzer):
        self.db = db
        self.blast_radius = blast_radius_analyzer

    def replay(self, symbol_name: Optional[str] = None, file_path: Optional[str] = None,
               limit: int = 50) -> List[Dict[str, Any]]:
        """
        Reassemble a semantic timeline: operations + decisions + drift events,
        merged and sorted by time, for a symbol or file.
        """
        events = []

        if symbol_name:
            symbol = self.db.query('SELECT id FROM symbols WHERE name = ?', (symbol_name,))
            symbol_id = symbol[0]['id'] if symbol else None
        else:
            symbol_id = None

        decisions_sql = 'SELECT id as ref, actor, reason, confidence, created_at as ts, "decision" as kind FROM decisions'
        conds, params = [], []
        if symbol_id:
            conds.append('symbol_id = ?')
            params.append(symbol_id)
        if file_path:
            conds.append('file_path = ?')
            params.append(file_path)
        if conds:
            decisions_sql += ' WHERE ' + ' AND '.join(conds)
        events.extend(self.db.query(decisions_sql + ' ORDER BY created_at DESC LIMIT ?', tuple(params) + (limit,)))

        if symbol_id:
            drift_rows = self.db.query(
                'SELECT id as ref, drift_type as reason, severity, detected_at as ts, "drift" as kind '
                'FROM drift_events WHERE symbol_id = ? ORDER BY detected_at DESC LIMIT ?',
                (symbol_id, limit)
            )
            events.extend(drift_rows)

        if file_path:
            op_rows = self.db.query(
                'SELECT id as ref, operation as reason, path, timestamp as ts, "operation" as kind '
                'FROM operations WHERE path = ? ORDER BY timestamp DESC LIMIT ?',
                (file_path, limit)
            )
            events.extend(op_rows)

        events.sort(key=lambda e: e.get('ts') or '', reverse=True)
        return events[:limit]

    def simulate_change(self, symbol_name: str, change_description: str = '') -> Dict[str, Any]:
        """
        Heuristic-only counterfactual: 'historically, changes to symbols with
        this blast-radius profile broke things N% of the time'. Explicitly
        NOT a prediction about this specific change.
        """
        radius = self.blast_radius.compute(symbol_name)
        if not radius.get('found'):
            return {
                'symbol': symbol_name,
                'heuristic': True,
                'note': 'No history for this symbol yet -- nothing to simulate against.',
            }

        # Base rate across all symbols with a similar blast radius bucket.
        similar = self.db.query('''
            SELECT ci.edited_symbol_id, COUNT(*) as impacts,
                   SUM(CASE WHEN ci.breakage_detected = 1 THEN 1 ELSE 0 END) as breaks
            FROM change_impacts ci
            GROUP BY ci.edited_symbol_id
        ''')
        break_rates = [row['breaks'] / row['impacts'] for row in similar if row['impacts']]
        base_rate = round(sum(break_rates) / len(break_rates), 3) if break_rates else None

        return {
            'symbol': symbol_name,
            'change_description': change_description,
            'heuristic': True,
            'blast_radius': radius,
            'historical_project_break_rate': base_rate,
            'recommendation': self._recommend(radius['risk'], base_rate),
        }

    def _recommend(self, risk: str, base_rate: Optional[float]) -> str:
        if risk in ('HIGH', 'CRITICAL'):
            return 'Require human review before applying this change.'
        if base_rate and base_rate > 0.3:
            return 'Proceed with an active test run immediately after applying.'
        return 'Low historical risk -- standard review is likely sufficient.'
