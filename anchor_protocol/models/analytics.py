"""AnalyticsEngine - Compute drift scores, hotspots, stability reports, I/O drift metrics."""

import math
from collections import Counter
from typing import Dict, Any, List


class AnalyticsEngine:
    def __init__(self, db):
        self.db = db

    def calculate_drift_score(self, symbol_id: int) -> float:
        recent_drifts = self.db.query("SELECT COUNT(*) as count FROM drift_events WHERE symbol_id = ? AND detected_at > datetime('now', '-7 days')", (symbol_id,))[0]['count']
        density = self.db.query('SELECT dependency_density FROM symbols WHERE id = ?', (symbol_id,))[0]['dependency_density'] or 0
        complexity = self.db.query('SELECT complexity_score FROM symbols WHERE id = ?', (symbol_id,))[0]['complexity_score'] or 0
        repairs = self.db.query("SELECT AVG(attempt_number) as avg FROM repair_loops WHERE symbol_id = ?", (symbol_id,))[0]['avg'] or 0
        # I/O contract drift weight
        io_drifts = self.db.query("SELECT COUNT(*) as count FROM io_contracts c JOIN drift_events d ON c.symbol_id = d.symbol_id WHERE c.symbol_id = ? AND d.detected_at > datetime('now', '-7 days')", (symbol_id,))[0]['count']
        score = (min(recent_drifts, 10) * 0.03) + (min(density, 2.0) * 0.12) + (min(complexity, 3.0) * 0.05) + (min(repairs, 5) * 0.03) + (min(io_drifts, 5) * 0.08)
        return min(score, 1.0)

    def calculate_entropy(self, symbol_id: int) -> float:
        drift_types = self.db.query('SELECT drift_type FROM drift_events WHERE symbol_id = ?', (symbol_id,))
        if not drift_types:
            return 0.0
        types = [row['drift_type'] for row in drift_types]
        counts = Counter(types)
        total = len(types)
        entropy = 0.0
        for count in counts.values():
            p = count / total
            entropy -= p * math.log2(p)
        return entropy

    def get_hotspots(self, limit: int = 10) -> List[Dict]:
        return self.db.query('SELECT file_path, drift_event_count, last_drift_at FROM drift_hotspots ORDER BY drift_event_count DESC LIMIT ?', (limit,))

    def get_top_risk_nodes(self, limit: int = 5) -> List[Dict]:
        symbols = self.db.query('SELECT id, name, file_id FROM symbols')
        scored = []
        for sym in symbols:
            score = self.calculate_drift_score(sym['id'])
            file_info = self.db.query('SELECT path FROM files WHERE id = ?', (sym['file_id'],))
            file_path = file_info[0]['path'] if file_info else 'unknown'
            scored.append({'name': sym['name'], 'file': file_path, 'drift_score': round(score, 2)})
        scored.sort(key=lambda x: x['drift_score'], reverse=True)
        return scored[:limit]

    def get_io_drift_metrics(self) -> Dict:
        """Get I/O contract drift specific metrics."""
        input_drifts = self.db.query("SELECT COUNT(*) as count FROM drift_events WHERE drift_type LIKE 'input_%'")[0]['count']
        output_drifts = self.db.query("SELECT COUNT(*) as count FROM drift_events WHERE drift_type LIKE 'output_%'")[0]['count']
        contract_count = self.db.query('SELECT COUNT(*) as count FROM io_contracts')[0]['count']
        return {
            'input_drifts': input_drifts,
            'output_drifts': output_drifts,
            'total_contracts': contract_count,
            'contract_coverage': round(contract_count / max(self.db.query('SELECT COUNT(*) as count FROM symbols')[0]['count'], 1), 2)
        }

    def generate_report(self, project_root: str) -> Dict[str, Any]:
        top_risks = self.get_top_risk_nodes(10)
        overall_score = sum(r['drift_score'] for r in top_risks) / len(top_risks) if top_risks else 0.0
        drift_summary = self.db.query("SELECT drift_type, COUNT(*) as count FROM drift_events WHERE detected_at > datetime('now', '-7 days') GROUP BY drift_type")
        repair_stats = self.db.query("SELECT AVG(attempt_number) as avg_attempts, MAX(attempt_number) as max_attempts FROM repair_loops")[0]
        hotspots = self.get_hotspots(5)
        silent = self.db.query("SELECT COUNT(*) as count FROM drift_events WHERE drift_type = 'silent_drift'")[0]['count']
        unresolved = self.db.query("SELECT COUNT(*) as count FROM drift_events WHERE resolved_at IS NULL")[0]['count']
        io_metrics = self.get_io_drift_metrics()
        return {
            'drift_score': round(overall_score, 2),
            'drift_level': self._score_level(overall_score),
            'top_risk_nodes': top_risks,
            'detected_drifts': {row['drift_type']: row['count'] for row in drift_summary},
            'silent_drifts': silent,
            'unresolved_drifts': unresolved,
            'repair_stats': {'avg_iterations': round(repair_stats['avg_attempts'] or 0, 1), 'max_iterations': repair_stats['max_attempts'] or 0},
            'hotspots': hotspots,
            'io_metrics': io_metrics,
            'entropy_analysis': self._get_entropy_summary()
        }

    def _score_level(self, score: float) -> str:
        if score < 0.2: return 'STABLE'
        elif score < 0.4: return 'LOW'
        elif score < 0.6: return 'MODERATE'
        elif score < 0.8: return 'HIGH'
        else: return 'CRITICAL'

    def _get_entropy_summary(self) -> List[Dict]:
        top = self.get_top_risk_nodes(5)
        result = []
        for node in top:
            symbol = self.db.query('SELECT id FROM symbols WHERE name = ?', (node['name'],))
            if symbol:
                entropy = self.calculate_entropy(symbol[0]['id'])
                result.append({'symbol': node['name'], 'entropy': round(entropy, 2), 'interpretation': 'Predictable' if entropy < 1.0 else 'Unpredictable' if entropy > 2.0 else 'Moderate'})
        return result