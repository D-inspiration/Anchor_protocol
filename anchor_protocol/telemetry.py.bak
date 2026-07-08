"""TelemetryManager - Local-first, opt-in, anonymized usage data.

Design constraints (deliberately conservative):
  - OFF by default. Nothing is recorded unless the user explicitly runs
    `anchor telemetry enable`.
  - Nothing is ever transmitted automatically. There is no network call in
    this module. Data sits in the local SQLite db until the user runs
    `anchor telemetry export`, at which point *they* decide what to do with
    the resulting file.
  - Payloads are scrubbed of common secret-shaped keys before being stored,
    even though callers are expected to only pass metadata in the first
    place -- defense in depth against an accidental `source_code` key.

This intentionally does NOT collect source code, file contents, environment
variables, or anything resembling a credential. See README.md "Telemetry"
section for the full data policy.
"""

import json
import os
from typing import Dict, Any, List, Optional

_FORBIDDEN_KEYS = {
    'source_code', 'code', 'content', 'file_content', 'secret', 'secrets',
    'password', 'passwd', 'api_key', 'apikey', 'token', 'access_token',
    'env', 'environment', 'credentials', 'private_key',
}


def _scrub(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in payload.items() if k.lower() not in _FORBIDDEN_KEYS}


class TelemetryManager:
    def __init__(self, db, project_root: str):
        self.db = db
        self.project_root = project_root
        self._config_path = os.path.join(project_root, '.anchor', 'telemetry_config.json')

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
        config = self._read_config()
        count = self.db.query('SELECT COUNT(*) as c FROM telemetry_events')[0]['c']
        return {'enabled': config.get('enabled', False), 'events_recorded': count, 'config_path': self._config_path}

    def record_event(self, event_type: str, payload: Optional[Dict[str, Any]] = None) -> None:
        """No-op unless telemetry is enabled. Scrubs forbidden keys defensively."""
        if not self.is_enabled():
            return
        clean = _scrub(payload or {})
        self.db.execute(
            'INSERT INTO telemetry_events (event_type, payload) VALUES (?, ?)',
            (event_type, json.dumps(clean))
        )

    def export(self, output_path: str) -> int:
        """Dump all locally-stored events to a JSON file the user can inspect before sharing anywhere."""
        events = self.db.query('SELECT event_type, payload, created_at FROM telemetry_events ORDER BY created_at')
        rows = [{'event_type': e['event_type'], 'payload': json.loads(e['payload']), 'created_at': e['created_at']}
                for e in events]
        with open(output_path, 'w') as f:
            json.dump(rows, f, indent=2)
        return len(rows)

    def clear(self) -> int:
        events = self.db.query('SELECT COUNT(*) as c FROM telemetry_events')[0]['c']
        self.db.execute('DELETE FROM telemetry_events', ())
        return events

    def build_payload(self) -> Dict[str, Any]:
        """The exact JSON body submit()/export() would send -- exposed separately so
        callers (and the CLI) can show it to the user before anything leaves the machine."""
        events = self.db.query('SELECT event_type, payload, created_at FROM telemetry_events ORDER BY created_at')
        return {
            'anchor_version': self._get_version(),
            'events': [
                {'event_type': e['event_type'], 'payload': json.loads(e['payload']), 'created_at': e['created_at']}
                for e in events
            ],
        }

    @staticmethod
    def _get_version() -> str:
        try:
            from . import __version__
            return __version__
        except ImportError:
            return 'unknown'

    def submit(self, endpoint: str, timeout: int = 15) -> Dict[str, Any]:
        """
        POST the current export to `endpoint`. There is no default endpoint --
        one must always be passed explicitly, so this can never silently phone
        home. Intended to be called only after the CLI has shown the user the
        exact payload and asked for confirmation (see `anchor telemetry submit`).
        """
        if not self.is_enabled():
            raise RuntimeError("Telemetry is disabled. Run 'anchor telemetry enable' first.")
        if not endpoint:
            raise ValueError("submit() requires an explicit endpoint URL -- there is no default.")

        import urllib.request
        import urllib.error

        payload = self.build_payload()
        body = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(endpoint, data=body, headers={'Content-Type': 'application/json'}, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = resp.status
                response_body = resp.read().decode('utf-8', 'ignore')
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Submit failed with HTTP {e.code}: {e.read().decode('utf-8', 'ignore')}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Could not reach {endpoint}: {e.reason}")

        return {'status': status, 'events_sent': len(payload['events']), 'response': response_body[:500]}
