"""BlastRadiusAnalyzer - 'terraform plan' for code changes.

Before an agent touches a symbol, answer: how many modules/functions does
this actually touch, transitively, and how risky does history say that is?
Walks the same `dependencies` table ImpactTracker already populates.
"""

from typing import Dict, Any, List, Set


class BlastRadiusAnalyzer:
    def __init__(self, db):
        self.db = db

    def compute(self, symbol_name: str, max_depth: int = 3) -> Dict[str, Any]:
        symbol = self.db.query('SELECT id FROM symbols WHERE name = ? ORDER BY created_at DESC LIMIT 1', (symbol_name,))
        if not symbol:
            return {'symbol': symbol_name, 'found': False}

        root_id = symbol[0]['id']
        visited: Set[int] = {root_id}
        frontier = [root_id]
        depth = 0
        touched_files = set()
        touched_symbols = []

        while frontier and depth < max_depth:
            next_frontier = []
            for sid in frontier:
                dependents = self.db.query(
                    'SELECT s.id, s.name, f.path FROM dependencies d '
                    'JOIN symbols s ON d.symbol_id = s.id '
                    'JOIN files f ON s.file_id = f.id '
                    'WHERE d.depends_on_symbol_id = ?',
                    (sid,)
                )
                for dep in dependents:
                    if dep['id'] not in visited:
                        visited.add(dep['id'])
                        next_frontier.append(dep['id'])
                        touched_files.add(dep['path'])
                        touched_symbols.append({'symbol': dep['name'], 'file': dep['path'], 'depth': depth + 1})
            frontier = next_frontier
            depth += 1

        # Historical risk signal: has this symbol caused breakage before?
        historical_breaks = self.db.query(
            'SELECT COUNT(*) as c FROM change_impacts WHERE edited_symbol_id = ? AND breakage_detected = 1',
            (root_id,)
        )[0]['c']
        drift_count = self.db.query(
            'SELECT COUNT(*) as c FROM drift_events WHERE symbol_id = ?', (root_id,)
        )[0]['c']

        risk = self._classify_risk(len(touched_symbols), len(touched_files), historical_breaks, drift_count)

        # Which contracts does this touch?
        contracts = self.db.query(
            'SELECT output_type FROM io_contracts WHERE symbol_id = ?', (root_id,)
        )

        return {
            'symbol': symbol_name,
            'found': True,
            'modules_touched': len(touched_files),
            'functions_touched': len(touched_symbols),
            'contracts_touched': len(contracts),
            'historical_breakages': historical_breaks,
            'historical_drift_events': drift_count,
            'risk': risk,
            'touched': touched_symbols,
        }

    def _classify_risk(self, n_symbols: int, n_files: int, historical_breaks: int, drift_count: int) -> str:
        score = n_symbols * 1 + n_files * 2 + historical_breaks * 5 + drift_count * 3
        if score == 0:
            return 'LOW'
        if score < 8:
            return 'MEDIUM'
        if score < 20:
            return 'HIGH'
        return 'CRITICAL'
