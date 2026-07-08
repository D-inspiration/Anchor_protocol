"""FileTrustManager - evidence-based trust tracking, not origin tracking.

The question this answers is "why should this change be trusted?", not
"did it come through an Anchor ticket?" A file accumulates a list of
evidence entries (each stamped with a content hash and timestamp); trust
state is derived by checking which evidence entries still match the file's
*current* hash, not stored as a single flag that can silently go stale.

Evidence types this version knows how to produce:
  - "anchor_scan"      : syntax + invariant checks passed (see sidecar.analyze_file)
  - "human_review"      : a person looked at it and vouched for it (see sidecar.mark_reviewed)
  - "manual_override"   : someone explicitly bypassed the check (audit trail, not "trust")

Not yet implemented, deliberately left as extension points (record_evidence
accepts any string type, so these can be added without a schema change):
  - "tests"    : e.g. a pytest hook maps failures/passes per file
  - "ruff" / "mypy" : static analysis tool integration
  - "multi_agent_consensus" : the SynvixOps-style multiple-validators idea

Display state (get_state) collapses the evidence list into one label for
convenience:
  - UNVERIFIED     : no evidence at all
  - STALE          : evidence exists, but none of it matches the current
                      content hash (file changed since last verified)
  - <TYPE>_VERIFIED / HUMAN_REVIEWED / etc: at least one evidence entry
                      matches the current hash; if several types are valid
                      simultaneously, all are returned in `valid_types`.
"""

import hashlib
import json
import time
from typing import Any, Dict, List, Optional


class FileTrustManager:
    def __init__(self, db, project_root: str):
        self.db = db
        self.project_root = project_root
        self._ensure_table()

    def _ensure_table(self) -> None:
        self.db.execute(
            'CREATE TABLE IF NOT EXISTS file_trust ('
            'path TEXT PRIMARY KEY, evidence_json TEXT DEFAULT \'[]\', '
            'updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)',
            ()
        )

    # -- hashing -------------------------------------------------------------

    @staticmethod
    def _hash_content(content: str) -> str:
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def _current_hash(self, rel_path: str) -> Optional[str]:
        import os
        full_path = os.path.join(self.project_root, rel_path)
        if not os.path.exists(full_path):
            return None
        with open(full_path, 'r') as f:
            return self._hash_content(f.read())

    # -- evidence --------------------------------------------------------

    def record_evidence(self, rel_path: str, evidence_type: str, detail: str = '',
                         actor: str = 'unknown') -> Dict[str, Any]:
        """Append one evidence entry, stamped with the file's *current*
        content hash. Does not overwrite prior evidence -- old entries just
        stop counting once the file changes again (their hash won't match).
        """
        current_hash = self._current_hash(rel_path)
        if current_hash is None:
            raise FileNotFoundError(f"Cannot record evidence for '{rel_path}': file does not exist")

        row = self.db.query_one('SELECT evidence_json FROM file_trust WHERE path = ?', (rel_path,))
        evidence = json.loads(row['evidence_json']) if row else []
        entry = {
            'type': evidence_type,
            'hash': current_hash,
            'timestamp': time.time(),
            'actor': actor,
            'detail': detail,
        }
        evidence.append(entry)

        self.db.execute(
            'INSERT INTO file_trust (path, evidence_json, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) '
            'ON CONFLICT(path) DO UPDATE SET evidence_json = excluded.evidence_json, updated_at = CURRENT_TIMESTAMP',
            (rel_path, json.dumps(evidence))
        )
        return entry

    def valid_evidence(self, rel_path: str) -> List[Dict[str, Any]]:
        """Evidence entries whose stamped hash matches the file's current
        content -- i.e. evidence that hasn't gone stale."""
        current_hash = self._current_hash(rel_path)
        if current_hash is None:
            return []
        row = self.db.query_one('SELECT evidence_json FROM file_trust WHERE path = ?', (rel_path,))
        if not row:
            return []
        evidence = json.loads(row['evidence_json'])
        return [e for e in evidence if e['hash'] == current_hash]

    def all_evidence(self, rel_path: str) -> List[Dict[str, Any]]:
        """Full evidence history, valid or not -- used to distinguish
        UNVERIFIED (never checked) from STALE (checked, but that was for a
        different version of the file)."""
        row = self.db.query_one('SELECT evidence_json FROM file_trust WHERE path = ?', (rel_path,))
        return json.loads(row['evidence_json']) if row else []

    # Evidence type -> human-facing state label. Falls back to
    # "<TYPE>_VERIFIED" for any evidence type not listed here, so new
    # evidence sources (tests, ruff, mypy, multi-agent consensus, ...) don't
    # need a code change here to get a reasonable label.
    _LABELS = {
        'anchor_scan': 'ANCHOR_VERIFIED',
        'human_review': 'HUMAN_REVIEWED',
        'manual_override': 'MANUAL_OVERRIDE',
        'tests': 'TEST_VERIFIED',
    }

    def get_state(self, rel_path: str) -> Dict[str, Any]:
        """One human-readable summary for a single file."""
        valid = self.valid_evidence(rel_path)
        history = self.all_evidence(rel_path)

        if valid:
            types = sorted({e['type'] for e in valid})
            label = '+'.join(self._LABELS.get(t, f'{t.upper()}_VERIFIED') for t in types)
        elif history:
            types = []
            label = 'STALE'
        else:
            types = []
            label = 'UNVERIFIED'

        return {
            'path': rel_path,
            'state': label,
            'valid_evidence_types': types,
            'valid_evidence_count': len(valid),
            'total_evidence_count': len(history),
        }

    def tracked_files(self) -> List[str]:
        rows = self.db.query('SELECT path FROM file_trust ORDER BY path', ())
        return [r['path'] for r in rows]

