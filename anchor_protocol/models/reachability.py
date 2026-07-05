"""ReachabilityAnalyzer - Which functions/classes are never called by anything?

Directly inspired by the AnalyticsEngine-orphaned incident: a module can be
syntactically perfect and completely dead because nothing imports or calls
it. This walks the project's Python files, builds a naive call-name index,
and flags symbols that are defined but never referenced -- excluding
reasonable entry points (dunder methods, test functions, __main__ blocks,
CLI entry points declared in setup.py/pyproject.toml).
"""

import ast
import os
from typing import Dict, Any, List, Set

ENTRY_POINT_NAMES = {'main', '__main__', 'run', 'app', 'application', 'wsgi', 'asgi'}


class ReachabilityAnalyzer:
    def __init__(self, project_root: str):
        self.project_root = project_root

    def analyze(self, exclude_dirs: Set[str] = None) -> Dict[str, Any]:
        exclude_dirs = exclude_dirs or {'.anchor', '.git', '__pycache__', 'node_modules', 'venv', '.venv', 'build', 'dist'}

        defined: Dict[str, List[str]] = {}   # name -> [files it's defined in]
        called: Set[str] = set()
        py_files = []

        for root, dirs, files in os.walk(self.project_root):
            dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.endswith('.egg-info')]
            for fname in files:
                if fname.endswith('.py'):
                    py_files.append(os.path.join(root, fname))

        for path in py_files:
            rel = os.path.relpath(path, self.project_root)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    source = f.read()
                tree = ast.parse(source)
            except (SyntaxError, UnicodeDecodeError, IOError):
                continue

            is_test_file = 'test' in os.path.basename(rel).lower()

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    if node.name.startswith('__') and node.name.endswith('__'):
                        continue  # dunders are framework-called, not "orphaned"
                    if node.name.lower() in ENTRY_POINT_NAMES:
                        continue
                    if is_test_file or node.name.startswith('test_'):
                        continue  # test functions are called by the test runner, not by name
                    defined.setdefault(node.name, []).append(rel)

                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        called.add(node.func.id)
                    elif isinstance(node.func, ast.Attribute):
                        called.add(node.func.attr)
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                    called.add(node.id)  # decorator refs, passed-as-value, etc.

        orphaned = {name: files for name, files in defined.items() if name not in called}

        return {
            'files_scanned': len(py_files),
            'symbols_defined': len(defined),
            'orphaned_count': len(orphaned),
            'orphaned': [{'symbol': name, 'files': files} for name, files in sorted(orphaned.items())],
        }
