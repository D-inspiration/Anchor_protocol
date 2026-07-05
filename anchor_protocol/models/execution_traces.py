"""ExecutionTraceManager - Record and replay function executions."""

import json
import uuid
import time
from typing import Dict, Any, Optional, List


class ExecutionTraceManager:
    """
    Records input→function→output traces for:
    - Replay debugging
    - Runtime mismatch detection
    - Stability scoring (same input → same output)
    """

    def __init__(self, db):
        self.db = db

    def record_trace(self, symbol_name: str, inputs: Dict[str, Any], output: Any,
                     execution_time_ms: float = None) -> str:
        """Record a function execution trace."""
        symbol = self.db.query('SELECT id FROM symbols WHERE name = ? ORDER BY created_at DESC LIMIT 1', (symbol_name,))
        if not symbol:
            raise ValueError(f'Symbol {symbol_name} not found')
        symbol_id = symbol[0]['id']
        call_id = str(uuid.uuid4())[:12]
        self.db.execute('INSERT INTO execution_traces (call_id, symbol_id, inputs, output, execution_time_ms) VALUES (?, ?, ?, ?, ?)',
                       (call_id, symbol_id, json.dumps(inputs, default=str), json.dumps(output, default=str), execution_time_ms or 0.0))
        return call_id

    def get_traces(self, symbol_name: str, limit: int = 50) -> List[Dict]:
        """Get execution traces for a symbol."""
        return self.db.query('''
            SELECT t.call_id, t.inputs, t.output, t.execution_time_ms, t.timestamp, s.name as symbol_name
            FROM execution_traces t
            JOIN symbols s ON t.symbol_id = s.id
            WHERE s.name = ?
            ORDER BY t.timestamp DESC
            LIMIT ?
        ''', (symbol_name, limit))

    def get_trace(self, call_id: str) -> Optional[Dict]:
        rows = self.db.query('''
            SELECT t.*, s.name as symbol_name
            FROM execution_traces t
            JOIN symbols s ON t.symbol_id = s.id
            WHERE t.call_id = ?
        ''', (call_id,))
        if rows:
            row = rows[0]
            return {
                'call_id': row['call_id'],
                'symbol': row['symbol_name'],
                'inputs': json.loads(row['inputs']),
                'output': json.loads(row['output']),
                'execution_time_ms': row['execution_time_ms'],
                'timestamp': row['timestamp']
            }
        return None

    def check_stability(self, symbol_name: str) -> Dict:
        """Check if same inputs produce same outputs over time."""
        traces = self.get_traces(symbol_name, limit=100)
        if len(traces) < 2:
            return {'stable': True, 'sample_size': len(traces), 'mismatch_rate': 0.0}

        # Group by input hash
        from collections import defaultdict
        groups = defaultdict(list)
        for t in traces:
            input_hash = hash(json.dumps(t['inputs'], sort_keys=True, default=str))
            groups[input_hash].append(t['output'])

        mismatches = 0
        total_groups = 0
        for outputs in groups.values():
            if len(outputs) > 1:
                total_groups += 1
                first = outputs[0]
                if not all(o == first for o in outputs[1:]):
                    mismatches += 1

        rate = mismatches / total_groups if total_groups else 0.0
        return {
            'stable': rate < 0.1,
            'sample_size': len(traces),
            'unique_inputs': len(groups),
            'mismatch_rate': round(rate, 3)
        }

    def find_runtime_mismatch(self, symbol_name: str, expected_output: Any, actual_output: Any) -> Optional[Dict]:
        """Record and flag a runtime output mismatch."""
        trace_id = self.record_trace(symbol_name, {}, actual_output)
        return {
            'trace_id': trace_id,
            'type': 'runtime_mismatch',
            'expected': expected_output,
            'actual': actual_output,
            'detected_at': time.time()
        }

    def get_execution_summary(self, symbol_name: str) -> Dict:
        """Summary stats for a function's execution history."""
        traces = self.get_traces(symbol_name, limit=1000)
        if not traces:
            return {'total_calls': 0}
        times = [t['execution_time_ms'] for t in traces if t['execution_time_ms']]
        return {
            'total_calls': len(traces),
            'avg_execution_time_ms': round(sum(times) / len(times), 2) if times else 0,
            'max_execution_time_ms': max(times) if times else 0,
            'stability': self.check_stability(symbol_name)
        }