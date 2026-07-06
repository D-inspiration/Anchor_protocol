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
        """
        Walk every .py file under project_root and record which symbols call
        which other symbols, including across files -- this is what powers
        blast_radius.py and predict_impact(). Paths are stored relative to
        project_root, matching every other path key in the system (files,
        active_files, io_contracts, etc.) -- this previously stored absolute
        paths from os.walk, which meant the dependency graph could never be
        looked up by anything else even on the rare occasions it was called.
        """
        all_symbols = []  # collect first so cross-file lookups can see everything
        parsed_files = {}
        for root, _, files in os.walk(project_root):
            if '.anchor' in root or '__pycache__' in root or '.git' in root:
                continue
            for file in files:
                if not file.endswith('.py'):
                    continue
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, project_root)
                try:
                    with open(full_path, 'r') as f:
                        content = f.read()
                    tree = ast.parse(content)
                    parsed_files[rel_path] = tree
                except (SyntaxError, IOError, UnicodeDecodeError):
                    continue

        # Build a project-wide name -> symbol_id map (best-effort; a real import
        # resolver would disambiguate same-named symbols across files, this
        # doesn't, but it's enough to catch the common "renamed and callers in
        # other files weren't updated" case this is meant to catch).
        name_to_symbol_id: Dict[str, int] = {}
        for rel_path in parsed_files:
            rows = self.db.query('SELECT id, name FROM symbols WHERE file_id = (SELECT id FROM files WHERE path = ?)', (rel_path,))
            for row in rows:
                name_to_symbol_id[row['name']] = row['id']

        for rel_path, tree in parsed_files.items():
            self._extract_dependencies(rel_path, tree, name_to_symbol_id)

    def _extract_dependencies(self, file_path: str, tree: ast.AST, name_to_symbol_id: Dict[str, int]):
        """For every function/method body in this file, record calls to any
        known project symbol (same file or a different one) as a dependency."""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                caller_row = self.db.query(
                    'SELECT id FROM symbols WHERE file_id = (SELECT id FROM files WHERE path = ?) AND name = ?',
                    (file_path, node.name)
                )
                if not caller_row:
                    continue
                caller_id = caller_row[0]['id']
                for child in ast.walk(node):
                    if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                        called_name = child.func.id
                        callee_id = name_to_symbol_id.get(called_name)
                        if callee_id and callee_id != caller_id:
                            self._add_dependency(caller_id, callee_id, 'calls')

    def _add_dependency(self, symbol_id: int, depends_on_id: int, dep_type: str):
        existing = self.db.query('SELECT id FROM dependencies WHERE symbol_id = ? AND depends_on_symbol_id = ?', (symbol_id, depends_on_id))
        if not existing:
            self.db.execute('INSERT INTO dependencies (symbol_id, depends_on_symbol_id, dependency_type) VALUES (?, ?, ?)', (symbol_id, depends_on_id, dep_type))