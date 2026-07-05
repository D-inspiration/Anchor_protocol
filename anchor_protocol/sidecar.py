"""Anchor Protocol sidecar."""

import os
import sys
import uuid
import json
import time
import hashlib
import shutil
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple

from .data.db import Database
from .optimizers.token_guard import TokenGuard
from .models.registry import Registry
from .models.io_contracts import IOContractManager
from .models.execution_traces import ExecutionTraceManager
from .models.drift import DriftTracker
from .models.impact import ImpactTracker
from .models.analytics import AnalyticsEngine
from .models.decisions import DecisionManager
from .models.assumptions import AssumptionManager
from .models.invariants import InvariantManager
from .models.trust import AgentTrustManager
from .models.blast_radius import BlastRadiusAnalyzer
from .models.simulation import SimulationEngine
from .models.incidents import IncidentManager
from .models.reachability import ReachabilityAnalyzer
from .telemetry import TelemetryManager
from .guardian import Guardian


# Context window budgeting constants
MAX_CONTEXT_TOKENS = 12000  # Leave 4k for LLM response on 16k context
TOKEN_PER_CHAR = 0.25  # Conservative estimate: ~4 chars per token
MAX_ACTIVE_FILES = 5
EXECUTION_TTL = 300  # seconds a proposal ticket stays valid
EXCLUDED_PATTERNS = [
    '.pyc', '__pycache__', '.anchor', '.git', '.zip',
    '.sqlite3', '.db', 'node_modules', '.venv', 'venv',
    '.env', '.env.local', '.env.production', 'egg-info',
    'build/', 'dist/', '.pytest_cache', '.mypy_cache'
]

# File role classification
ROLE_CONTEXT = 'context'    # Read-only: models, settings, contracts
ROLE_ACTIVE = 'active'      # Editable: views, services, controllers
ROLE_FROZEN = 'frozen'      # Protected: migrations, __init__, generated code


@dataclass
class EditProposal:
    """A proposed edit to a single file, pending Guardian validation."""
    path: str
    old_content: str
    new_content: str
    reason: str = ''
    symbol_name: Optional[str] = None
    change_type: str = 'edit'
    actor: str = 'unknown'
    confidence: float = 1.0


@dataclass
class FileReadResult:
    path: str
    content: str
    hash: str


def estimate_tokens(file_path: str) -> int:
    """Estimate token count for a file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return int(len(content) * TOKEN_PER_CHAR)
    except (IOError, UnicodeDecodeError):
        return 0


def classify_file_role(rel_path: str) -> str:
    """Classify a file's role based on path/name."""
    basename = os.path.basename(rel_path)
    dirname = os.path.dirname(rel_path)

    if basename in ('__init__.py', '__main__.py'):
        return ROLE_FROZEN
    if 'migrations' in dirname or 'migration' in basename:
        return ROLE_FROZEN
    if basename.endswith(('.min.js', '.bundle.js', '.css.map')):
        return ROLE_FROZEN

    if basename in ('models.py', 'settings.py', 'admin.py', 'schema.py', 'types.py'):
        return ROLE_CONTEXT
    if 'contract' in basename or 'schema' in basename:
        return ROLE_CONTEXT

    if basename in ('views.py', 'services.py', 'controllers.py', 'handlers.py', 'api.py'):
        return ROLE_ACTIVE
    if 'test' in basename or 'spec' in basename:
        return ROLE_ACTIVE

    return ROLE_CONTEXT


def filter_excluded(files: List[str]) -> List[str]:
    """Remove build artifacts and cache files."""
    result = []
    for f in files:
        if any(pattern in f for pattern in EXCLUDED_PATTERNS):
            continue
        result.append(f)
    return result


def budget_files_by_role(files: List[str], project_path: str, max_tokens: int = MAX_CONTEXT_TOKENS) -> Tuple[Dict[str, List[str]], int, int]:
    """Distribute files across roles within token budget. Returns: {role: files}, total_tokens, skipped_count"""
    role_files = {ROLE_CONTEXT: [], ROLE_ACTIVE: [], ROLE_FROZEN: []}
    for f in files:
        role = classify_file_role(f)
        role_files[role].append(f)

    priority_order = [ROLE_CONTEXT, ROLE_ACTIVE, ROLE_FROZEN]
    result = {ROLE_CONTEXT: [], ROLE_ACTIVE: [], ROLE_FROZEN: []}
    total_tokens = 0

    for role in priority_order:
        if role == ROLE_CONTEXT:
            sorted_files = sorted(role_files[role], key=lambda f: estimate_tokens(os.path.join(project_path, f)))
        else:
            sorted_files = role_files[role]

        for f in sorted_files:
            tokens = estimate_tokens(os.path.join(project_path, f))
            if role == ROLE_FROZEN:
                result[role].append(f)
                total_tokens += tokens
                continue
            if total_tokens + tokens > max_tokens:
                break
            result[role].append(f)
            total_tokens += tokens

    skipped = len(files) - sum(len(v) for v in result.values())
    return result, total_tokens, skipped


class AnchorSidecar:
    """AI governance sidecar: zero-trust file mediation + tiered scope + token budgeting."""

    def __init__(self, project_root: str):
        self.project_root = os.path.abspath(project_root)
        self.db = Database(self.project_root)
        self.token_guard = TokenGuard()
        self.registry = Registry(self.db)
        self.io_contracts = IOContractManager(self.db)
        self.execution_traces = ExecutionTraceManager(self.db)
        self.drift_tracker = DriftTracker(self.db)
        self.impact_tracker = ImpactTracker(self.db)
        self.analytics = AnalyticsEngine(self.db)
        self.guardian = Guardian(self.project_root, self.db)

        # Governance layer
        self.decisions = DecisionManager(self.db)
        self.assumptions = AssumptionManager(self.db)
        self.invariants = InvariantManager(self.db)
        self.trust = AgentTrustManager(self.db)
        self.blast_radius = BlastRadiusAnalyzer(self.db)
        self.simulation = SimulationEngine(self.db, self.blast_radius)
        self.incidents = IncidentManager(self.db)
        self.reachability = ReachabilityAnalyzer(self.project_root)
        self.telemetry = TelemetryManager(self.db, self.project_root)

        # Tiered scope
        self.session_id: Optional[str] = None
        self.context_files: List[str] = []
        self.active_files: List[str] = []
        self.frozen_files: List[str] = []

        self._pending_tickets: Dict[str, Dict[str, Any]] = {}

    # -- session -------------------------------------------------------

    def init_session(self, session_id: Optional[str] = None, reuse_existing: bool = True) -> str:
        """Initialize or load session with tiered scope."""
        self.db.init_schema()

        if session_id:
            self.session_id = session_id
            row = self.db.query(
                'SELECT context_files, active_files, frozen_files FROM sessions WHERE session_id = ?',
                (session_id,)
            )
            if not row:
                raise ValueError(f"Session {session_id} not found")
            self.context_files = json.loads(row[0]['context_files'] or '[]')
            self.active_files = json.loads(row[0]['active_files'] or '[]')
            self.frozen_files = json.loads(row[0]['frozen_files'] or '[]')
            return self.session_id

        if reuse_existing:
            row = self.db.query(
                'SELECT session_id, context_files, active_files, frozen_files FROM sessions WHERE project_root = ? ORDER BY created_at DESC LIMIT 1',
                (self.project_root,)
            )
            if row:
                self.session_id = row[0]['session_id']
                self.context_files = json.loads(row[0]['context_files'] or '[]')
                self.active_files = json.loads(row[0]['active_files'] or '[]')
                self.frozen_files = json.loads(row[0]['frozen_files'] or '[]')
                return self.session_id

        self.session_id = str(uuid.uuid4())[:8]
        self.token_guard.reset()
        self.save_scope()
        return self.session_id

    def set_scope(self, files: List[str], project_path: Optional[str] = None) -> Dict[str, Any]:
        """Set tiered scope automatically (role classification + token budgeting)."""
        path = project_path or self.project_root
        clean_files = filter_excluded(files)
        budgeted, total_tokens, skipped = budget_files_by_role(clean_files, path)

        self.context_files = budgeted[ROLE_CONTEXT]
        self.active_files = budgeted[ROLE_ACTIVE]
        self.frozen_files = budgeted[ROLE_FROZEN]
        self.save_scope()

        return {
            'context_count': len(self.context_files),
            'active_count': len(self.active_files),
            'frozen_count': len(self.frozen_files),
            'total_tokens': total_tokens,
            'skipped': skipped,
            'budget_percent': round((total_tokens / MAX_CONTEXT_TOKENS) * 100, 1)
        }

    def set_manual_scope(self, active_files: Optional[List[str]] = None,
                          frozen_files: Optional[List[str]] = None,
                          context_files: Optional[List[str]] = None) -> None:
        """Directly control scope tiers (bypasses auto role classification/budgeting)."""
        active_files = active_files if active_files is not None else self.active_files
        if len(active_files) > MAX_ACTIVE_FILES:
            raise ValueError(f"Cannot set more than {MAX_ACTIVE_FILES} active files (got {len(active_files)})")

        self.active_files = list(active_files)
        if frozen_files is not None:
            self.frozen_files = list(frozen_files)
        if context_files is not None:
            self.context_files = list(context_files)
        self.save_scope()

    def save_scope(self):
        """Persist tiered scope to database."""
        self.db.execute('''
            INSERT INTO sessions (session_id, project_root, context_files, active_files, frozen_files, created_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(session_id) DO UPDATE SET
                context_files = excluded.context_files,
                active_files = excluded.active_files,
                frozen_files = excluded.frozen_files,
                updated_at = datetime('now')
        ''', (
            self.session_id, self.project_root,
            json.dumps(self.context_files), json.dumps(self.active_files), json.dumps(self.frozen_files)
        ))

    # -- zero-trust read/write mediation --------------------------------

    def _abs_path(self, rel_path: str) -> str:
        return os.path.normpath(os.path.join(self.project_root, rel_path))

    def read_file(self, rel_path: str) -> FileReadResult:
        """Read a file through Guardian's sandbox/forbidden-path checks."""
        full_path = self._abs_path(rel_path)
        result = self.guardian.validate_read(full_path, self.active_files, self.frozen_files, rel_path=rel_path)
        if not result.success:
            raise PermissionError(result.error)

        self.token_guard.check_read_budget(rel_path)
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
        self.token_guard.record_read(rel_path, len(content))

        file_hash = hashlib.sha256(content.encode()).hexdigest()
        self.db.log_operation(self.session_id, 'read', rel_path, file_hash)

        try:
            self.registry.extract_symbols(full_path, content)
        except Exception:
            pass

        return FileReadResult(path=rel_path, content=content, hash=file_hash)

    def propose_edit(self, proposal: EditProposal) -> str:
        """Validate scope + budget for a proposed edit and issue a ticket."""
        full_path = self._abs_path(proposal.path)
        result = self.guardian.validate_proposal(full_path, proposal, self.active_files, self.frozen_files, rel_path=proposal.path)
        if not result.success:
            raise PermissionError(result.error)

        self.token_guard.check_edit_budget(proposal.path, len(proposal.new_content))

        ticket_id = str(uuid.uuid4())[:12]
        self._pending_tickets[ticket_id] = {'proposal': proposal, 'created_at': time.time()}
        self.db.store_proposal(ticket_id, self.session_id, proposal)
        return ticket_id

    def execute_ticket(self, ticket_id: str) -> Dict[str, Any]:
        """Execute a previously issued edit ticket: precondition -> syntax -> write -> record.

        Tickets are looked up in-memory first (fast path within one process),
        falling back to the DB-persisted proposal so a ticket issued by one
        CLI invocation (e.g. `anchor propose`) can be executed by a later,
        separate invocation (e.g. `anchor execute`) -- this is required for
        any external agent that drives Anchor purely through the CLI rather
        than holding a single long-lived AnchorSidecar object.
        """
        ticket = self._pending_tickets.get(ticket_id)
        if ticket:
            proposal: EditProposal = ticket['proposal']
            created_at = ticket['created_at']
        else:
            persisted = self.db.get_proposal(ticket_id)
            if not persisted:
                raise ValueError(f"Unknown or expired ticket: {ticket_id}")
            proposal, created_at_str = persisted
            created_at = self._parse_db_timestamp(created_at_str)

        if time.time() - created_at > EXECUTION_TTL:
            self._pending_tickets.pop(ticket_id, None)
            raise ValueError(f"Ticket {ticket_id} expired (TTL {EXECUTION_TTL}s)")
        full_path = self._abs_path(proposal.path)

        with open(full_path, 'r', encoding='utf-8') as f:
            current_content = f.read()

        ok, err = self.guardian.check_semantic_precondition(proposal.old_content, current_content, proposal.path)
        if not ok:
            self.trust.record_operation(proposal.actor, contract_compliant=False)
            raise ValueError(f"Semantic precondition failed: {err}")

        ok, err = self.guardian.validate_syntax(proposal.new_content, proposal.path)
        if not ok:
            self.trust.record_operation(proposal.actor, contract_compliant=False)
            raise ValueError(f"Syntax validation failed: {err}")

        invariant_hits = self.invariants.check_source(proposal.path, proposal.new_content)
        for hit in invariant_hits:
            self.invariants.record_violation(hit['invariant_id'], proposal.path, hit['detail'])

        backup_path = f"{full_path}.anchor.bak"
        shutil.copy2(full_path, backup_path)

        try:
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(proposal.new_content)

            new_hash = hashlib.sha256(proposal.new_content.encode()).hexdigest()
            self.db.log_operation(self.session_id, 'write', proposal.path, new_hash)
            self.token_guard.record_edit(proposal.path, len(proposal.new_content))

            try:
                self.registry.extract_symbols(full_path, proposal.new_content)
            except Exception:
                pass

            self.trust.record_operation(proposal.actor, contract_compliant=True,
                                         invariant_compliant=(len(invariant_hits) == 0))

            self.telemetry.record_event('propose_edit', {
                'agent': proposal.actor,
                'operation': 'propose_edit',
                'contracts_checked': len(invariant_hits) + 1,
                'contracts_failed': len(invariant_hits),
                'drift_detected': False,
                'language': os.path.splitext(proposal.path)[1].lstrip('.') or 'unknown',
            })

            self._pending_tickets.pop(ticket_id, None)
            return {
                'success': True, 'path': proposal.path, 'hash': new_hash,
                'backup': backup_path, 'invariant_violations': invariant_hits,
            }
        except Exception:
            shutil.copy2(backup_path, full_path)
            raise

    @staticmethod
    def _parse_db_timestamp(ts: str) -> float:
        """SQLite's CURRENT_TIMESTAMP is UTC and naive ('YYYY-MM-DD HH:MM:SS'); convert to epoch seconds."""
        import datetime
        dt = datetime.datetime.strptime(ts, '%Y-%m-%d %H:%M:%S').replace(tzinfo=datetime.timezone.utc)
        return dt.timestamp()

    def detect_drift(self, rel_path: str) -> List[Dict[str, Any]]:
        """Compare currently-registered symbols for a file against its current AST."""
        full_path = self._abs_path(rel_path)
        previous = {s['name'] for s in self.registry.get_symbols_for_file(full_path)}

        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
        try:
            new_symbols = self.registry.extract_symbols(full_path, content)
        except Exception:
            return []
        current = {s['name'] for s in new_symbols}

        drifts = []
        for missing in previous - current:
            drifts.append({'type': 'missing_symbol', 'symbol': missing, 'path': rel_path})
            self.drift_tracker.record_drift(None, 'missing_symbol', severity='high')
        for added in current - previous:
            drifts.append({'type': 'silent_drift', 'symbol': added, 'path': rel_path})
            self.drift_tracker.record_drift(None, 'silent_drift', severity='low')
        return drifts

    # -- reporting / governance queries ----------------------------------

    def get_stability_report(self):
        return self.analytics.generate_report(self.project_root)

    def compute_trust_score(self, symbol_name: str) -> float:
        """Symbol trust score (0.0 = unreliable, 1.0 = solid): 1.0 - (drifts*0.05 + repairs*0.15 + impacts*0.25)"""
        symbol = self.db.query('SELECT id FROM symbols WHERE name = ? LIMIT 1', (symbol_name,))
        if not symbol:
            return 1.0

        sid = symbol[0]['id']
        drifts = self.db.query('SELECT COUNT(*) as c FROM drift_events WHERE symbol_id = ?', (sid,))[0]['c']
        repairs = self.db.query('SELECT COUNT(*) as c FROM repair_loops WHERE symbol_id = ?', (sid,))[0]['c']
        impacts = self.db.query(
            'SELECT COUNT(*) as c FROM change_impacts WHERE edited_symbol_id = ? AND breakage_detected = 1', (sid,)
        )[0]['c']

        raw = 1.0 - (drifts * 0.05 + repairs * 0.15 + impacts * 0.25)
        return max(0.0, min(1.0, raw))
