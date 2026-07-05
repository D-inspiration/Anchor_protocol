"""Guardian - Zero-trust policy enforcer with semantic validation."""

import os
import re
import ast
import json
import subprocess
from typing import Optional, Tuple
from dataclasses import dataclass


@dataclass
class ValidationResult:
    success: bool
    error: Optional[str] = None


class Guardian:
    FORBIDDEN_PATTERNS = [
        r'\.env',
        r'__pycache__',
        r'\.git',
        r'\.ssh',
        r'\.anchor',
    ]

    def __init__(self, project_root: str, db):
        self.project_root = project_root
        self.db = db

    def _is_forbidden(self, path: str) -> bool:
        for pattern in self.FORBIDDEN_PATTERNS:
            if re.search(pattern, path):
                return True
        return False

    def _is_within_project(self, path: str) -> bool:
        real_path = os.path.realpath(path)
        real_root = os.path.realpath(self.project_root)
        return real_path.startswith(real_root)

    def validate_read(self, path: str, active_files: list, frozen_files: list, rel_path: str = None) -> ValidationResult:
        if not self._is_within_project(path):
            return ValidationResult(False, "SecurityViolation: Path outside project root")
        if self._is_forbidden(path):
            return ValidationResult(False, "SecurityViolation: Forbidden path")
        return ValidationResult(True)

    def validate_proposal(self, path: str, proposal, active_files: list, frozen_files: list, rel_path: str = None) -> ValidationResult:
        if not self._is_within_project(path):
            return ValidationResult(False, "SecurityViolation: Path outside project root")
        if self._is_forbidden(path):
            return ValidationResult(False, "SecurityViolation: Forbidden path")
        scope_key = rel_path if rel_path is not None else path
        if scope_key in frozen_files:
            return ValidationResult(False, "ScopeViolation: File is frozen")
        if scope_key not in active_files:
            return ValidationResult(False, "ScopeViolation: File not in active set")
        return ValidationResult(True)

    def check_semantic_precondition(self, old_content: str, current_content: str, path: str) -> Tuple[bool, Optional[str]]:
        if not path.endswith('.py'):
            if old_content != current_content:
                return False, "Content mismatch (non-Python file)"
            return True, None

        try:
            old_tree = ast.parse(old_content)
            current_tree = ast.parse(current_content)
            old_dump = ast.dump(old_tree, annotate_fields=False)
            current_dump = ast.dump(current_tree, annotate_fields=False)
            if old_dump != current_dump:
                return False, "Semantic drift detected (AST mismatch)"
            return True, None
        except SyntaxError:
            if old_content != current_content:
                return False, "Content mismatch (unparseable Python)"
            return True, None

    def validate_syntax(self, content: str, path: str) -> Tuple[bool, Optional[str]]:
        ext = os.path.splitext(path)[1].lower()
        if ext == '.py':
            return self._validate_python(content)
        elif ext == '.json':
            return self._validate_json(content)
        elif ext in ('.yaml', '.yml'):
            return self._validate_yaml(content)
        elif ext == '.sh':
            return self._validate_shell(content)
        else:
            return True, None

    def _validate_python(self, content: str) -> Tuple[bool, Optional[str]]:
        try:
            ast.parse(content)
            return True, None
        except SyntaxError as e:
            return False, f"Python syntax error: {e}"

    def _validate_json(self, content: str) -> Tuple[bool, Optional[str]]:
        try:
            json.loads(content)
            return True, None
        except json.JSONDecodeError as e:
            return False, f"JSON error: {e}"

    def _validate_yaml(self, content: str) -> Tuple[bool, Optional[str]]:
        try:
            import yaml
        except ImportError:
            return False, ("YAML validation requires the optional 'yaml' extra: "
                            "pip install anchor-protocol[yaml]")
        try:
            yaml.safe_load(content)
            return True, None
        except Exception as e:
            return False, f"YAML error: {e}"

    def _validate_shell(self, content: str) -> Tuple[bool, Optional[str]]:
        try:
            result = subprocess.run(['bash', '-n'], input=content, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return True, None
            return False, f"Shell syntax error: {result.stderr}"
        except Exception as e:
            return False, f"Shell validation failed: {e}"