"""SymbolRegistry - Code symbol extraction and management."""

import os
import ast
import json
import hashlib
from typing import List, Dict, Any


class SymbolRegistry:
    def __init__(self, db):
        self.db = db

    def extract_symbols(self, file_path: str, content: str) -> List[Dict[str, Any]]:
        if not file_path.endswith('.py'):
            return []
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return []
        symbols = []
        file_id = self._get_or_create_file(file_path, content)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                symbol = self._extract_symbol(node, file_path, content)
                symbol_id = self._store_symbol(file_id, symbol)
                symbol['id'] = symbol_id
                symbols.append(symbol)
        return symbols

    def _extract_symbol(self, node, file_path: str, content: str) -> Dict[str, Any]:
        start_line = node.lineno
        end_line = node.end_lineno if hasattr(node, 'end_lineno') else start_line
        branch_count = self._count_branches(node)
        complexity = (end_line - start_line) * 0.01 + branch_count * 0.05
        arguments = []
        return_annotation = None
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for arg in node.args.args:
                arg_info = {'name': arg.arg}
                if arg.annotation:
                    arg_info['annotation'] = ast.unparse(arg.annotation) if hasattr(ast, 'unparse') else str(arg.annotation)
                arguments.append(arg_info)
            if node.returns:
                return_annotation = ast.unparse(node.returns) if hasattr(ast, 'unparse') else str(node.returns)
        arg_str = ', '.join([a['name'] for a in arguments])
        signature = f'{node.name}({arg_str})'
        if return_annotation:
            signature += f' -> {return_annotation}'
        return {
            'name': node.name,
            'symbol_type': 'function' if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else 'class',
            'start_line': start_line,
            'end_line': end_line,
            'signature': signature,
            'return_annotation': return_annotation,
            'arguments': json.dumps(arguments),
            'complexity_score': complexity,
            'dependency_density': 0.0
        }

    def _count_branches(self, node) -> int:
        count = 0
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.ExceptHandler)):
                count += 1
        return count

    def _get_or_create_file(self, path: str, content: str) -> int:
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:16]
        result = self.db.query('SELECT id FROM files WHERE path = ?', (path,))
        if result:
            file_id = result[0]['id']
            self.db.execute('UPDATE files SET last_hash = ?, last_seen = CURRENT_TIMESTAMP WHERE id = ?', (hash_val, file_id))
            return file_id
        return self.db.execute('INSERT INTO files (path, last_hash, last_seen) VALUES (?, ?, CURRENT_TIMESTAMP)', (path, hash_val))

    def _store_symbol(self, file_id: int, symbol: Dict) -> int:
        result = self.db.query('SELECT id FROM symbols WHERE file_id = ? AND name = ?', (file_id, symbol['name']))
        if result:
            symbol_id = result[0]['id']
            self.db.execute('UPDATE symbols SET symbol_type = ?, start_line = ?, end_line = ?, signature = ?, return_annotation = ?, arguments = ?, complexity_score = ? WHERE id = ?',
                          (symbol['symbol_type'], symbol['start_line'], symbol['end_line'], symbol['signature'], symbol['return_annotation'], symbol['arguments'], symbol['complexity_score'], symbol_id))
            return symbol_id
        return self.db.execute('INSERT INTO symbols (file_id, name, symbol_type, start_line, end_line, signature, return_annotation, arguments, complexity_score, dependency_density, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)',
                              (file_id, symbol['name'], symbol['symbol_type'], symbol['start_line'], symbol['end_line'], symbol['signature'], symbol['return_annotation'], symbol['arguments'], symbol['complexity_score'], symbol['dependency_density']))

    def get_symbols_for_file(self, file_path: str) -> List[Dict]:
        result = self.db.query('SELECT id FROM files WHERE path = ?', (file_path,))
        if not result:
            return []
        file_id = result[0]['id']
        return self.db.query('SELECT * FROM symbols WHERE file_id = ?', (file_id,))

    def update_dependency_density(self, symbol_id: int):
        callers = self.db.query('SELECT COUNT(*) as count FROM dependencies WHERE depends_on_symbol_id = ?', (symbol_id,))[0]['count']
        dependencies = self.db.query('SELECT COUNT(*) as count FROM dependencies WHERE symbol_id = ?', (symbol_id,))[0]['count']
        density = (callers + dependencies) / 10.0
        self.db.execute('UPDATE symbols SET dependency_density = ? WHERE id = ?', (density, symbol_id))


class Registry(SymbolRegistry):
    """Backward-compatible wrapper with additional registry methods."""
    
    def get_stability_metrics(self):
        """Aggregate stability data for report generation."""
        return self.db.query('''
            SELECT s.name, s.complexity_score, s.dependency_density,
                   COUNT(d.id) as drift_count
            FROM symbols s
            LEFT JOIN drift_events d ON d.symbol_id = s.id
            GROUP BY s.id
            ORDER BY drift_count DESC
        ''')
        