"""ImpactTracker - Track change impact and downstream effects."""

import ast
import os
from typing import List, Dict, Optional


class ImpactTracker:
    def __init__(self, db):
        self.db = db

    def predict_impact(self, file_path: str, symbol_name: Optional[str]) -> List[Dict]:
        if not symbol_name:
            return []
        symbol = self.db.query('SELECT s.id, f.path FROM symbols s JOIN files f ON s.file_id = f.id WHERE s.name = ? AND f.path = ?', (symbol_name, file_path))
        if not symbol:
            return []
        symbol_id = symbol[0]['id']
        dependents = self.db.query('SELECT s.name, f.path, d.dependency_type FROM dependencies d JOIN symbols s ON d.symbol_id = s.id JOIN files f ON s.file_id = f.id WHERE d.depends_on_symbol_id = ?', (symbol_id,))
        return [{'symbol': row['name'], 'file': row['path'], 'relationship': row['dependency_type']} for row in dependents]

    def record_change(self, change_id: str, edited_symbol: str, file_path: str):
        symbol = self.db.query('SELECT id FROM symbols WHERE name = ? AND file_id = (SELECT id FROM files WHERE path = ?)', (edited_symbol, file_path))
        if not symbol:
            return
        edited_id = symbol[0]['id']
        affected = self.db.query('SELECT symbol_id FROM dependencies WHERE depends_on_symbol_id = ?', (edited_id,))
        for row in affected:
            self.db.execute('INSERT INTO change_impacts (change_id, edited_symbol_id, affected_symbol_id) VALUES (?, ?, ?)', (change_id, edited_id, row['symbol_id']))

    def scan_dependencies(self, project_root: str):
        for root, _, files in os.walk(project_root):
            for file in files:
                if not file.endswith('.py'):
                    continue
                path = os.path.join(root, file)
                try:
                    with open(path, 'r') as f:
                        content = f.read()
                    tree = ast.parse(content)
                    self._extract_dependencies(path, tree)
                except:
                    pass

    def _extract_dependencies(self, file_path: str, tree: ast.AST):
        file_symbols = self.db.query('SELECT id, name FROM symbols WHERE file_id = (SELECT id FROM files WHERE path = ?)', (file_path,))
        symbol_map = {s['name']: s['id'] for s in file_symbols}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    called_name = node.func.id
                    for sym_name, sym_id in symbol_map.items():
                        if called_name == sym_name or called_name.startswith(sym_name + '.'):
                            caller = next((s for s in file_symbols if s['name'] != sym_name), None)
                            if caller:
                                self._add_dependency(caller['id'], sym_id, 'calls')

    def _add_dependency(self, symbol_id: int, depends_on_id: int, dep_type: str):
        existing = self.db.query('SELECT id FROM dependencies WHERE symbol_id = ? AND depends_on_symbol_id = ?', (symbol_id, depends_on_id))
        if not existing:
            self.db.execute('INSERT INTO dependencies (symbol_id, depends_on_symbol_id, dependency_type) VALUES (?, ?, ?)', (symbol_id, depends_on_id, dep_type))