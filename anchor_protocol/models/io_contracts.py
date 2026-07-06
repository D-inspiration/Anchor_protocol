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

    @staticmethod
    def _infer_literal_type(node) -> str:
        """Best-effort type inference from an actual AST expression (dict/list literals,
        constants, etc.), used as a fallback when there's no PEP 484 annotation to read."""
        import ast
        if node is None:
            return 'Any'
        if isinstance(node, ast.Dict):
            return 'dict'
        if isinstance(node, ast.List):
            return 'list'
        if isinstance(node, ast.Tuple):
            return 'tuple'
        if isinstance(node, ast.Set):
            return 'set'
        if isinstance(node, ast.Constant):
            if node.value is None:
                return 'None'
            return type(node.value).__name__
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            # e.g. dict(...), list(...), MyClass(...)
            return node.func.id
        return 'Any'

    def detect_input_drift(self, symbol_name: str, new_source: str) -> List[Dict]:
        """Detect if function signature changed vs declared contract.

        Falls back to reading actual default-value literals when there's no
        PEP 484 annotation, so unannotated code (the common case) doesn't
        permanently mismatch a declared contract just because it was never
        type-hinted in the first place.

        If the symbol no longer exists at all, returns a single
        'symbol_removed' entry instead of an empty list -- an empty list
        previously looked identical to "no drift found," which is wrong:
        a deleted/renamed-away symbol is the most severe possible drift,
        not a clean pass.
        """
        contract = self.get_contract(symbol_name)
        if not contract:
            return []
        import ast
        try:
            tree = ast.parse(new_source)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == symbol_name:
                    current_inputs = {}
                    for arg in node.args.args:
                        if arg.annotation and hasattr(ast, 'unparse'):
                            current_inputs[arg.arg] = ast.unparse(arg.annotation)
                        else:
                            current_inputs[arg.arg] = None  # unknown -- don't compare, don't flag
                    drifts = []
                    expected = contract['inputs']
                    for key in expected:
                        if key not in current_inputs:
                            drifts.append({'type': 'input_removed', 'param': key, 'severity': 'high'})
                        elif current_inputs[key] is not None and current_inputs[key] != expected[key]:
                            drifts.append({'type': 'input_type_changed', 'param': key, 'expected': expected[key], 'actual': current_inputs[key], 'severity': 'high'})
                    for key in current_inputs:
                        if key not in expected:
                            drifts.append({'type': 'input_added', 'param': key, 'severity': 'low'})
                    return drifts
            # Walked the whole tree, no FunctionDef/AsyncFunctionDef named symbol_name found.
            return [{'type': 'symbol_removed', 'severity': 'critical'}]
        except Exception:
            pass
        return []

    def detect_output_drift(self, symbol_name: str, new_source: str) -> Optional[Dict]:
        """Detect if return type changed vs declared contract.

        Uses the PEP 484 return annotation when present; otherwise infers a
        type from the actual literal(s) returned. Two failure modes are kept
        explicitly distinct rather than collapsed into a generic mismatch:
          - the symbol is gone entirely -> 'symbol_removed' (critical)
          - the symbol exists but the return shape can't be statically
            resolved (e.g. a BinOp or f-string) -> 'output_type_unknown',
            with actual='unresolved', NOT a fabricated 'Any' that looks like
            a confidently-inferred type when it isn't one.
        """
        contract = self.get_contract(symbol_name)
        if not contract:
            return None
        import ast
        try:
            tree = ast.parse(new_source)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == symbol_name:
                    if node.returns and hasattr(ast, 'unparse'):
                        current_output = ast.unparse(node.returns)
                    else:
                        inferred_types = set()
                        for child in ast.walk(node):
                            if isinstance(child, ast.Return) and child.value is not None:
                                inferred_types.add(self._infer_literal_type(child.value))
                        if not inferred_types:
                            return None  # no annotation, no literal return to infer from -- don't guess
                        if 'Any' in inferred_types:
                            # We genuinely couldn't resolve at least one return shape (e.g. a
                            # BinOp like `"x" + str(y)`, or an f-string). Don't report this as
                            # if it were a real, confidently-inferred type -- it isn't one.
                            return {'type': 'output_type_unknown', 'expected': contract['output_type'],
                                    'actual': 'unresolved', 'severity': 'low',
                                    'note': 'could not statically infer the new return type'}
                        current_output = inferred_types.pop() if len(inferred_types) == 1 else '|'.join(sorted(inferred_types))
                    if current_output != contract['output_type']:
                        return {'type': 'output_type_changed', 'expected': contract['output_type'], 'actual': current_output, 'severity': 'high'}
                    return None
            # Walked the whole tree, no matching FunctionDef/AsyncFunctionDef found at all.
            return {'type': 'symbol_removed', 'expected': contract['output_type'], 'actual': None, 'severity': 'critical'}
        except Exception:
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