"""InvariantManager - Rules that must survive every edit, refactor, or migration.

Invariants sit above dependency graphs and contracts: "an order cannot exist
without a customer" doesn't care what language the codebase is in. Anchor
can't prove arbitrary invariants automatically, but it can (a) keep them as
a first-class declared registry so agents and humans see them before editing,
and (b) run cheap, real static checks against a small set of expressible
invariant kinds so violations get caught mechanically where possible.
"""

import ast
import re
from typing import Dict, Any, List, Optional


class InvariantManager:
    """
    check_expr encodes one of a small set of *mechanically checkable* invariant
    kinds. Anything else is stored as documentation-only (checked manually /
    by an agent, but Anchor won't silently claim it verified something it
    didn't).

    Supported check kinds:
      - "no_bare_except"            : function/file must not use bare `except:`
      - "must_call:<name>"          : function body must call `<name>` somewhere
      - "must_not_call:<name>"      : function body must never call `<name>`
      - "field_required:<name>"     : dataclass/class must define a field named <name>
      - "return_not_none"           : function must not have a bare `return` / `return None`
      - "path_invariant"            : paths must be built with os.path.join/pathlib, not
                                       raw string concatenation -- the exact bug class that
                                       caused the project_root vs db_path incident.
    Anything else -> treated as a documentation-only invariant.
    """

    MECHANICAL_KINDS = ('no_bare_except', 'must_call:', 'must_not_call:', 'field_required:',
                         'return_not_none', 'path_invariant')

    def __init__(self, db):
        self.db = db

    def declare_invariant(self, name: str, description: str, scope: Optional[str] = None,
                           severity: str = 'high', check_expr: Optional[str] = None) -> int:
        existing = self.db.query('SELECT id FROM invariants WHERE name = ?', (name,))
        if existing:
            self.db.execute(
                'UPDATE invariants SET description = ?, scope = ?, severity = ?, check_expr = ? WHERE id = ?',
                (description, scope, severity, check_expr, existing[0]['id'])
            )
            return existing[0]['id']
        return self.db.execute(
            'INSERT INTO invariants (name, description, scope, severity, check_expr) VALUES (?, ?, ?, ?, ?)',
            (name, description, scope, severity, check_expr)
        )

    def list_invariants(self, scope: Optional[str] = None) -> List[Dict[str, Any]]:
        if scope:
            return self.db.query('SELECT * FROM invariants WHERE scope = ? ORDER BY severity DESC', (scope,))
        return self.db.query('SELECT * FROM invariants ORDER BY severity DESC')

    def is_mechanically_checkable(self, check_expr: Optional[str]) -> bool:
        if not check_expr:
            return False
        return any(check_expr == k or check_expr.startswith(k) for k in self.MECHANICAL_KINDS)

    def check_source(self, path: str, source: str, scope: Optional[str] = None) -> List[Dict[str, Any]]:
        """Run all mechanically-checkable invariants (optionally scoped) against source. Returns violations."""
        violations = []
        invariants = self.list_invariants(scope=scope)
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return violations

        for inv in invariants:
            expr = inv['check_expr']
            if not self.is_mechanically_checkable(expr):
                continue
            hit = self._run_check(expr, tree, source)
            if hit:
                violations.append({
                    'invariant_id': inv['id'],
                    'invariant': inv['name'],
                    'severity': inv['severity'],
                    'path': path,
                    'detail': hit,
                })
        return violations

    def record_violation(self, invariant_id: int, path: str, detail: str) -> int:
        return self.db.execute(
            'INSERT INTO invariant_violations (invariant_id, path, detail) VALUES (?, ?, ?)',
            (invariant_id, path, detail)
        )

    def get_violations(self, invariant_id: Optional[int] = None) -> List[Dict[str, Any]]:
        if invariant_id:
            return self.db.query(
                'SELECT * FROM invariant_violations WHERE invariant_id = ? ORDER BY detected_at DESC', (invariant_id,)
            )
        return self.db.query('''
            SELECT v.*, i.name as invariant_name, i.severity
            FROM invariant_violations v
            JOIN invariants i ON v.invariant_id = i.id
            ORDER BY v.detected_at DESC
        ''')

    # -- mechanical checks --------------------------------------------------

    def _run_check(self, expr: str, tree: ast.AST, source: str) -> Optional[str]:
        if expr == 'no_bare_except':
            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler) and node.type is None:
                    return f"bare 'except:' at line {node.lineno}"
            return None

        if expr == 'return_not_none':
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    for child in ast.walk(node):
                        if isinstance(child, ast.Return) and (child.value is None or
                           (isinstance(child.value, ast.Constant) and child.value.value is None)):
                            return f"'{node.name}' returns None at line {child.lineno}"
            return None

        if expr == 'path_invariant':
            hits = self._find_raw_path_concat(tree)
            if hits:
                return f"raw path concatenation at line(s) {', '.join(str(l) for l in hits)} -- use os.path.join/pathlib instead"
            return None

        if expr.startswith('must_call:'):
            target = expr.split(':', 1)[1]
            calls = self._all_call_names(tree)
            if target not in calls:
                return f"required call to '{target}' not found"
            return None

        if expr.startswith('must_not_call:'):
            target = expr.split(':', 1)[1]
            calls = self._all_call_names(tree)
            if target in calls:
                return f"forbidden call to '{target}' found"
            return None

        if expr.startswith('field_required:'):
            target = expr.split(':', 1)[1]
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    field_names = set()
                    for child in node.body:
                        if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                            field_names.add(child.target.id)
                        if isinstance(child, ast.Assign):
                            for t in child.targets:
                                if isinstance(t, ast.Name):
                                    field_names.add(t.id)
                    if target not in field_names:
                        return f"class '{node.name}' missing required field '{target}'"
            return None

        return None

    def _find_raw_path_concat(self, tree: ast.AST) -> List[int]:
        """
        Heuristic: flag `a + '/' + b`-style BinOp concatenation involving a
        string literal that contains a path separator. Doesn't catch
        everything (that's not possible statically in general), but catches
        the common case that caused the project_root/db_path bug.
        """
        hits = []
        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
                for side in (node.left, node.right):
                    if isinstance(side, ast.Constant) and isinstance(side.value, str) and (
                        '/' in side.value or '\\' in side.value
                    ):
                        hits.append(node.lineno)
                        break
        return hits

    def _all_call_names(self, tree: ast.AST) -> set:
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    names.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    names.add(node.func.attr)
        return names
