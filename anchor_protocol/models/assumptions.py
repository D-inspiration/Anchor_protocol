"""AssumptionManager - Track hidden beliefs agents encode into code.

Most AI-driven drift doesn't come from bad syntax -- it comes from an agent
silently assuming something ("there's only one payment provider") that was
true when the code was written and false by the time it's changed again.
This module makes those beliefs first-class and queryable instead of implicit.
"""

from typing import Dict, Any, List, Optional


class AssumptionManager:
    def __init__(self, db):
        self.db = db

    def record_assumption(self, text: str, symbol_name: Optional[str] = None,
                           source: str = 'manual') -> int:
        """
        source: 'manual' (developer-declared) or 'inferred' (agent-guessed).
        """
        symbol_id = None
        if symbol_name:
            symbol = self.db.query(
                'SELECT id FROM symbols WHERE name = ? ORDER BY created_at DESC LIMIT 1', (symbol_name,)
            )
            if symbol:
                symbol_id = symbol[0]['id']
        return self.db.execute(
            'INSERT INTO assumptions (symbol_id, text, source) VALUES (?, ?, ?)',
            (symbol_id, text, source)
        )

    def list_assumptions(self, symbol_name: Optional[str] = None, active_only: bool = True) -> List[Dict[str, Any]]:
        if symbol_name:
            sql = '''
                SELECT a.*, s.name as symbol_name FROM assumptions a
                JOIN symbols s ON a.symbol_id = s.id
                WHERE s.name = ?
            '''
            params = (symbol_name,)
        else:
            sql = '''
                SELECT a.*, s.name as symbol_name FROM assumptions a
                LEFT JOIN symbols s ON a.symbol_id = s.id
                WHERE 1 = 1
            '''
            params = ()
        if active_only:
            sql += " AND a.status = 'active'"
        sql += " ORDER BY a.created_at DESC"
        return self.db.query(sql, params)

    def flag_violation(self, assumption_id: int, evidence: str) -> None:
        """Mark an assumption as violated -- e.g. a second payment provider showed up."""
        self.db.execute(
            "UPDATE assumptions SET status = 'violated', violated_at = CURRENT_TIMESTAMP, "
            "violation_evidence = ? WHERE id = ?",
            (evidence, assumption_id)
        )

    def retire_assumption(self, assumption_id: int) -> None:
        """Assumption no longer applies (e.g. superseded by a real invariant)."""
        self.db.execute("UPDATE assumptions SET status = 'retired' WHERE id = ?", (assumption_id,))

    def get_violated(self) -> List[Dict[str, Any]]:
        return self.db.query('''
            SELECT a.*, s.name as symbol_name FROM assumptions a
            LEFT JOIN symbols s ON a.symbol_id = s.id
            WHERE a.status = 'violated'
            ORDER BY a.violated_at DESC
        ''')

    def scan_for_singleton_language(self, source_code: str) -> List[str]:
        """
        Heuristic scan for common phrasing that signals an unstated single-value
        assumption in *comments/docstrings* (e.g. 'only one', 'always', 'never').
        This is a nudge for a human/agent to declare the assumption explicitly,
        not a proof of anything.
        """
        import re
        hits = []
        patterns = [r'\bonly one\b', r'\balways\b', r'\bnever\b', r'\bassum(e|ing|ption)\b']
        for line_no, line in enumerate(source_code.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith('#') or stripped.startswith('"""') or stripped.startswith("'''"):
                for pat in patterns:
                    if re.search(pat, stripped, re.IGNORECASE):
                        hits.append(f"line {line_no}: {stripped[:80]}")
                        break
        return hits
