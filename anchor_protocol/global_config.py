"""GlobalTelemetryConfig - the one piece of Anchor state that lives outside
any single project, at ~/.anchor/config.json.

This deliberately holds only sync *preferences* (installation id, sync
mode/thresholds, last-sync bookkeeping). It never holds an endpoint override
by default and never holds event data -- event payloads stay in each
project's own local .anchor/anchor.db until that project explicitly syncs.

Schema:
{
  "installation_id": "8f4d5d1d-...",     // generated once, on first read
  "telemetry": {
    "mode": "manual",                     // "manual" | "auto_time" | "auto_count"
    "sync_interval_hours": 24,
    "sync_threshold_events": 100,
    "last_sync_unix": 0,
    "auto_sync_confirmed": false,         // set true only when the user explicitly
                                           // opts into auto_time/auto_count, see
                                           // cli.py's interactive `telemetry enable`
    "endpoint_override": null             // only set if the user explicitly configures one
  }
}
"""

import json
import os
import uuid
from typing import Any, Dict

CONFIG_PATH = os.path.expanduser('~/.anchor/config.json')

_DEFAULT_TELEMETRY = {
    'mode': 'manual',
    'sync_interval_hours': 24,
    'sync_threshold_events': 100,
    'last_sync_unix': 0,
    'auto_sync_confirmed': False,
    'endpoint_override': None,
}


def _default_config() -> Dict[str, Any]:
    return {'installation_id': str(uuid.uuid4()), 'telemetry': dict(_DEFAULT_TELEMETRY)}


def load() -> Dict[str, Any]:
    """Read ~/.anchor/config.json, creating it with a fresh installation_id
    on first use. Missing keys are backfilled with defaults so older config
    files on disk don't break when new fields are added here."""
    if not os.path.exists(CONFIG_PATH):
        config = _default_config()
        save(config)
        return config
    try:
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)
    except (json.JSONDecodeError, IOError):
        config = _default_config()
        save(config)
        return config

    if 'installation_id' not in config:
        config['installation_id'] = str(uuid.uuid4())
    telemetry = config.get('telemetry', {})
    for key, value in _DEFAULT_TELEMETRY.items():
        telemetry.setdefault(key, value)
    config['telemetry'] = telemetry
    return config


def save(config: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=2)


def update_telemetry(**fields: Any) -> Dict[str, Any]:
    """Merge `fields` into the telemetry section and persist. Returns the
    full config for convenience."""
    config = load()
    config['telemetry'].update(fields)
    save(config)
    return config


def installation_id() -> str:
    return load()['installation_id']

