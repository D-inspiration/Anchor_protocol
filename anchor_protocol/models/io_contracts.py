"""IOContractManager - Behavioral contract tracking for function I/O."""

import json
from typing import Dict, Any, Optional, List


class IOContractManager:
    """
    Tracks function-level I/O contracts:
    - inputs: dict of param_name -> type_hint
    - output_type: expected return type
    - side_effects: list of external effects (file writes, network calls)
    - confidence: 0.0-1.0 (1.0 = developer-declared, <1.0 = inferred)
    """

    def __init__(self, db):
        self.db = db

    def declare_contract(self, symbol_name: str, inputs: Dict[str, str], output_type: str,
                        side_effects: List[str] = None, confidence: float = 1.0) -> int:
        """Developer-declared I/O contract for a function."""
        symbol = self.db.query('SELECT id FROM symbols WHERE name = ? ORDER BY created_at DESC LIMIT 1', (symbol_name,))
        if not symbol:
            raise ValueError(f'Symbol {symbol_name} not found in registry')
        symbol_id = symbol[0]['id']
        existing = self.db.query('SELECT id FROM io_contracts WHERE symbol_id = ?', (symbol_id,))
        data = {
            'symbol_id': symbol_id,
            'inputs': json.dumps(inputs),
            'output_type': output_type,
            'side_effects': json.dumps(side_effects or []),
            'confidence': confidence
        }
        if existing:
            self.db.execute('UPDATE io_contracts SET inputs = ?, output_type = ?, side_effects = ?, confidence = ? WHERE id = ?',
                          (data['inputs'], data['output_type'], data['side_effects'], confidence, existing[0]['id']))
            return existing[0]['id']
        return self.db.execute('INSERT INTO io_contracts (symbol_id, inputs, output_type, side_effects, confidence) VALUES (?, ?, ?, ?, ?)',
                              (symbol_id, data['inputs'], data['output_type'], data['side_effects'], confidence))

    def infer_contract(self, symbol_name: str, source_code: str) -> Optional[Dict]:
        """Infer I/O contract from function signature using AST."""
        import ast
        try:
            tree = ast.parse(source_code)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == symbol_name:
                    inputs = {}
                    for arg in node.args.args:
                        if arg.annotation:
                            inputs[arg.arg] = ast.unparse(arg.annotation) if hasattr(ast, 'unparse') else str(arg.annotation)
                        else:
                            inputs[arg.arg] = 'Any'
                    output_type = ast.unparse(node.returns) if (node.returns and hasattr(ast, 'unparse')) else 'Any'
                    return self.declare_contract(symbol_name, inputs, output_type, confidence=0.7)
        except:
            pass
        return None

    def get_contract(self, symbol_name: str) -> Optional[Dict]:
        """Retrieve I/O contract for a symbol."""
        rows = self.db.query('''
            SELECT c.*, s.name as symbol_name, f.path as file_path
            FROM io_contracts c
            JOIN symbols s ON c.symbol_id = s.id
            JOIN files f ON s.file_id = f.id
            WHERE s.name = ?
            ORDER BY c.declared_at DESC LIMIT 1
        ''', (symbol_name,))
        if not rows:
            return None
        row = rows[0]
        return {
            'symbol': row['symbol_name'],
            'file': row['file_path'],
            'inputs': json.loads(row['inputs']),
            'output_type': row['output_type'],
            'side_effects': json.loads(row['side_effects']),
            'confidence': row['confidence'],
            'declared_at': row['declared_at']
        }

    def detect_input_drift(self, symbol_name: str, new_source: str) -> List[Dict]:
        """Detect if function signature changed vs declared contract."""
        contract = self.get_contract(symbol_name)
        if not contract:
            return []
        import ast
        try:
            tree = ast.parse(new_source)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == symbol_name:
                    current_inputs = {arg.arg: (ast.unparse(arg.annotation) if (arg.annotation and hasattr(ast, 'unparse')) else 'Any') for arg in node.args.args}
                    drifts = []
                    expected = contract['inputs']
                    for key in expected:
                        if key not in current_inputs:
                            drifts.append({'type': 'input_removed', 'param': key, 'severity': 'high'})
                        elif current_inputs[key] != expected[key]:
                            drifts.append({'type': 'input_type_changed', 'param': key, 'expected': expected[key], 'actual': current_inputs[key], 'severity': 'high'})
                    for key in current_inputs:
                        if key not in expected:
                            drifts.append({'type': 'input_added', 'param': key, 'severity': 'low'})
                    return drifts
        except:
            pass
        return []

    def detect_output_drift(self, symbol_name: str, new_source: str) -> Optional[Dict]:
        """Detect if return type changed vs declared contract."""
        contract = self.get_contract(symbol_name)
        if not contract:
            return None
        import ast
        try:
            tree = ast.parse(new_source)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == symbol_name:
                    current_output = ast.unparse(node.returns) if (node.returns and hasattr(ast, 'unparse')) else 'Any'
                    if current_output != contract['output_type']:
                        return {'type': 'output_type_changed', 'expected': contract['output_type'], 'actual': current_output, 'severity': 'high'}
        except:
            pass
        return None

    def list_all_contracts(self) -> List[Dict]:
        rows = self.db.query('''
            SELECT s.name, c.inputs, c.output_type, c.confidence, f.path
            FROM io_contracts c
            JOIN symbols s ON c.symbol_id = s.id
            JOIN files f ON s.file_id = f.id
            ORDER BY c.confidence DESC
        ''')
        return [{'symbol': r['name'], 'file': r['path'], 'inputs': json.loads(r['inputs']),
                 'output_type': r['output_type'], 'confidence': r['confidence']} for r in rows]