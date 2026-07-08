"""TelemetryManager - Local-first, opt-in, anonymized usage data.

Design constraints (deliberately conservative):
  - OFF by default. Nothing is recorded unless the user explicitly runs
    `anchor telemetry enable`.
  - Nothing is ever transmitted without the user having explicitly opted
    into *sending*, not just *recording*. `submit()` requires an explicit
    endpoint and only runs against events this project hasn't already sent.
  - Auto-sync (background, unattended sending) is a separate, stronger
    opt-in from "telemetry enabled": it only activates after the user
    explicitly confirms it once, in `anchor telemetry enable`'s interactive
    flow. Manual mode -- the default -- never sends anything without an
    explicit `anchor telemetry sync` invocation.
  - Payloads are scrubbed of common secret-shaped keys before being stored,
    even though callers are expected to only pass metadata in the first
    place -- defense in depth against an accidental `source_code` key.

This intentionally does NOT collect source code, file contents, environment
variables, or anything resembling a credential. See docs/telemetry.md and
PRIVACY.md for the full data policy.
"""

import json
import os
import time
from typing import Dict, Any, List, Optional

# There is no default endpoint baked into the network path itself --
# DEFAULT_ENDPOINT below is a suggestion the CLI may offer, never something
# submit() falls back to silently. submit() always requires an explicit
# endpoint argument (see its docstring).
DEFAULT_ENDPOINT = "https://auth.atrivix.com/telemetry/upload"

_FORBIDDEN_KEYS = {
    'source_code', 'code', 'content', 'file_content', 'secret', 'secrets',
    'password', 'passwd', 'api_key', 'apikey', 'token', 'access_token',
    'env', 'environment', 'credentials', 'private_key',
}

# Path-shaped keys are useful for correlating events (e.g. "the same file keeps
# drifting") without needing to know *which* file that is on someone's machine.
# Rather than dropping them (losing that correlation) or keeping them raw
# (leaking a real path -- this was a real bug: sidecar.py's edit_executed event
# was sending proposal.path verbatim), hash them.
_PATH_KEYS = {'path', 'file_path', 'filepath'}


def _scrub(payload: Dict[str, Any]) -> Dict[str, Any]:
    import hashlib
    clean = {}
    for k, v in payload.items():
        if k.lower() in _FORBIDDEN_KEYS:
            continue
        if k.lower() in _PATH_KEYS and isinstance(v, str):
            clean[k] = hashlib.sha256(v.encode('utf-8')).hexdigest()[:8]
        else:
            clean[k] = v
    return clean


class TelemetryManager:
    def __init__(self, db, project_root: str):
        self.db = db
        self.project_root = project_root
        self._config_path = os.path.join(project_root, '.anchor', 'telemetry_config.json')
        # NOTE: deliberately not called here. TelemetryManager is constructed in
        # AnchorSidecar.__init__(), before init_session() has run db.init_schema()
        # and created telemetry_events in the first place -- so this is called
        # lazily, right before anything touches the synced_at column, instead.

    # -- schema bootstrap (defensive, not a migration -- see note below) --

    def _ensure_synced_at_column(self) -> None:
        """Add telemetry_events.synced_at if it isn't there yet.

        This intentionally isn't a versioned .sql migration: Database.init_schema()
        runs migrations *before* creating base tables, so a migration that ALTERs
        telemetry_events would fail on a fresh install where that table doesn't
        exist yet. Checking PRAGMA table_info and adding the column on demand
        sidesteps that ordering problem and is idempotent either way.
        """
        try:
            columns = self.db.query("PRAGMA table_info(telemetry_events)")
        except Exception:
            return  # table doesn't exist yet (e.g. init_schema() hasn't run) -- next call will retry
        names = {c['name'] for c in columns}
        if columns and 'synced_at' not in names:
            self.db.execute('ALTER TABLE telemetry_events ADD COLUMN synced_at TIMESTAMP DEFAULT NULL', ())

    # -- per-project on/off config --------------------------------------

    def _read_config(self) -> Dict[str, Any]:
        if not os.path.exists(self._config_path):
            return {'enabled': False}
        try:
            with open(self._config_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {'enabled': False}

    def _write_config(self, config: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(self._config_path), exist_ok=True)
        with open(self._config_path, 'w') as f:
            json.dump(config, f, indent=2)

    def is_enabled(self) -> bool:
        return bool(self._read_config().get('enabled', False))

    def enable(self) -> None:
        self._write_config({'enabled': True})

    def disable(self) -> None:
        self._write_config({'enabled': False})

    def status(self) -> Dict[str, Any]:
        self._ensure_synced_at_column()
        config = self._read_config()
        count = self.db.query('SELECT COUNT(*) as c FROM telemetry_events')[0]['c']
        pending = self.db.query('SELECT COUNT(*) as c FROM telemetry_events WHERE synced_at IS NULL')[0]['c']
        return {
            'enabled': config.get('enabled', False),
            'events_recorded': count,
            'events_pending': pending,
            'config_path': self._config_path,
        }

    # -- recording ---------------------------------------------------------

    def record_event(self, event_type: str, payload: Optional[Dict[str, Any]] = None) -> None:
        """No-op unless telemetry is enabled. Scrubs forbidden keys defensively."""
        if not self.is_enabled():
            return
        clean = _scrub(payload or {})
        self.db.execute(
            'INSERT INTO telemetry_events (event_type, payload) VALUES (?, ?)',
            (event_type, json.dumps(clean))
        )

    # -- queue introspection ("pending" = not yet synced) -------------------

    def pending_count(self) -> int:
        self._ensure_synced_at_column()
        return self.db.query('SELECT COUNT(*) as c FROM telemetry_events WHERE synced_at IS NULL')[0]['c']

    def pending_summary(self) -> Dict[str, Any]:
        """Everything `anchor telemetry pending` needs to print, in one call."""
        payload = self.build_payload(unsynced_only=True)
        size_bytes = len(json.dumps(payload).encode('utf-8'))
        return {
            'enabled': self.is_enabled(),
            'pending_events': len(payload['events']),
            'estimated_upload_bytes': size_bytes,
        }

    # -- export / payload construction --------------------------------------

    def export(self, output_path: str) -> int:
        """Dump all locally-stored events (synced or not) to a JSON file the
        user can inspect before sharing anywhere."""
        self._ensure_synced_at_column()
        events = self.db.query('SELECT event_type, payload, created_at, synced_at FROM telemetry_events ORDER BY created_at')
        rows = [{'event_type': e['event_type'], 'payload': json.loads(e['payload']),
                 'created_at': e['created_at'], 'synced_at': e['synced_at']}
                for e in events]
        with open(output_path, 'w') as f:
            json.dump(rows, f, indent=2)
        return len(rows)

    def clear(self) -> int:
        events = self.db.query('SELECT COUNT(*) as c FROM telemetry_events')[0]['c']
        self.db.execute('DELETE FROM telemetry_events', ())
        return events

    def _pending_rows(self, unsynced_only: bool) -> List[Dict[str, Any]]:
        self._ensure_synced_at_column()
        if unsynced_only:
            return self.db.query(
                'SELECT id, event_type, payload, created_at FROM telemetry_events WHERE synced_at IS NULL ORDER BY created_at'
            )
        return self.db.query(
            'SELECT id, event_type, payload, created_at FROM telemetry_events ORDER BY created_at'
        )

    def build_payload(self, unsynced_only: bool = True) -> Dict[str, Any]:
        """The exact JSON body submit() would send -- a single batch envelope,
        exposed separately so callers (and the CLI's --dry-run) can show it to
        the user before anything leaves the machine.

        Shape: { installation_id, anchor_version, events: [ {operation,
        provider, [language], [contracts], [drift_detected], [metadata]}, ...
        ] } -- installation_id/anchor_version are stated once for the whole
        batch rather than repeated per event. This is a batching contract the
        server needs to support explicitly (accept an `events` array, apply
        the shared installation_id to each row) -- it is not yet what the
        deployed single-event endpoint validates; see docs/telemetry.md.

        unsynced_only=True (the default, and what submit() always uses) means
        a sync only ever includes events this project hasn't already sent --
        it will not resend history on every call.
        """
        rows = self._pending_rows(unsynced_only)
        from . import global_config
        return {
            'installation_id': global_config.installation_id(),
            'anchor_version': self._get_version(),
            'events': [self._to_wire_event(r['event_type'], json.loads(r['payload'])) for r in rows],
        }

    # Keys promoted to a top-level field on each wire event, so they're not
    # duplicated inside `metadata` too. 'agent' (the specific model, e.g.
    # "gemini-3.1-flash-lite") deliberately stays in metadata even when it's
    # used as a fallback for `provider` below -- it's more specific than
    # provider and still useful.
    _PROMOTED_KEYS = {'provider', 'language', 'io_contracts_checked', 'io_contracts_failed',
                       'structural_drift', 'drift_detected'}

    @classmethod
    def _to_wire_event(cls, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Map one internal (event_type, payload) row onto one item of the
        server's `events` array: operation, provider, [language],
        [contracts:{checked,failed}], [drift_detected], [metadata]. Does NOT
        include installation_id/anchor_version -- those are set once at the
        envelope level by build_payload(), not repeated per event.
        """
        out: Dict[str, Any] = {
            'provider': payload.get('provider') or payload.get('agent', 'unknown'),
            'operation': event_type,
        }
        if 'language' in payload:
            out['language'] = payload['language']

        if 'io_contracts_checked' in payload or 'io_contracts_failed' in payload:
            out['contracts'] = {
                'checked': payload.get('io_contracts_checked', 0),
                'failed': payload.get('io_contracts_failed', 0),
            }

        if 'drift_detected' in payload:
            out['drift_detected'] = payload['drift_detected']
        elif 'structural_drift' in payload:
            out['drift_detected'] = bool(payload['structural_drift'])

        metadata = {k: v for k, v in payload.items() if k not in cls._PROMOTED_KEYS}
        if metadata:
            out['metadata'] = metadata

        return out

    @staticmethod
    def _get_version() -> str:
        try:
            from . import __version__
            return __version__
        except ImportError:
            return 'unknown'

    # -- sending -------------------------------------------------------------

    def submit(self, endpoint: str, timeout: int = 15, api_key: Optional[str] = None) -> Dict[str, Any]:
        """
        POST unsynced events to `endpoint`. There is no default endpoint --
        one must always be passed explicitly, so this can never silently
        phone home. Intended to be called only after the CLI has shown the
        user the exact payload and asked for confirmation, or after the user
        has explicitly confirmed auto-sync once (see `anchor telemetry enable`).

        `api_key`, if not passed explicitly, is read from the
        ANCHOR_TELEMETRY_API_KEY environment variable. It is intentionally
        never hardcoded here or stored in any config file this repo ships --
        see docs/telemetry.md for how to provision one. A missing key is not
        treated as fatal at this layer (the server decides whether to accept
        an unauthenticated/rejected request); this just controls what header
        gets sent.

        On success, every event included in the payload is marked synced_at
        so a later call doesn't resend it.
        """
        if not self.is_enabled():
            raise RuntimeError("Telemetry is disabled. Run 'anchor telemetry enable' first.")
        if not endpoint:
            raise ValueError("submit() requires an explicit endpoint URL -- there is no default.")

        import urllib.request
        import urllib.error

        rows = self._pending_rows(unsynced_only=True)
        if not rows:
            return {'status': None, 'events_sent': 0, 'response': '(nothing pending)'}
        from . import global_config
        payload = {
            'installation_id': global_config.installation_id(),
            'anchor_version': self._get_version(),
            'events': [self._to_wire_event(r['event_type'], json.loads(r['payload'])) for r in rows],
        }
        event_ids = [r['id'] for r in rows]

        key = api_key if api_key is not None else os.environ.get('ANCHOR_TELEMETRY_API_KEY', 'your-256-bit-secret-here')
        headers = {
            'Content-Type': 'application/json',
            'X-Anchor-Client': f'anchor-protocol-python/{self._get_version()}',
        }
        if key:
            headers['X-Anchor-API-Key'] = key

        body = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(endpoint, data=body, headers=headers, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = resp.status
                response_body = resp.read().decode('utf-8', 'ignore')
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Submit failed with HTTP {e.code}: {e.read().decode('utf-8', 'ignore')}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Could not reach {endpoint}: {e.reason}")

        placeholders = ','.join('?' * len(event_ids))
        self.db.execute(
            f'UPDATE telemetry_events SET synced_at = CURRENT_TIMESTAMP WHERE id IN ({placeholders})',
            tuple(event_ids)
        )

        return {'status': status, 'events_sent': len(event_ids), 'response': response_body[:500]}

    # -- auto-sync eligibility (the decision only; sending itself still goes
    #    through submit(), so all its safety checks still apply) --------------

    def should_auto_sync(self, global_telemetry_config: Dict[str, Any]) -> bool:
        """Pure decision function: given the global sync-preferences dict
        (see global_config.py), should an auto-sync fire right now?

        Requires ALL of:
          - telemetry enabled for this project
          - mode is auto_time or auto_count (never for "manual", the default)
          - the user has explicitly confirmed auto-sync at least once
          - the relevant threshold (time or event count) is actually met
        """
        if not self.is_enabled():
            return False
        if not global_telemetry_config.get('auto_sync_confirmed'):
            return False

        mode = global_telemetry_config.get('mode', 'manual')
        if mode == 'auto_time':
            last_sync = global_telemetry_config.get('last_sync_unix', 0)
            interval_seconds = global_telemetry_config.get('sync_interval_hours', 24) * 3600
            return (time.time() - last_sync) >= interval_seconds and self.pending_count() > 0
        elif mode == 'auto_count':
            threshold = global_telemetry_config.get('sync_threshold_events', 100)
            return self.pending_count() >= threshold
        return False

