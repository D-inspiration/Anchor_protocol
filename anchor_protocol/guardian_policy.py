"""Per-project pre-commit trust policy: .anchor/guardian_policy.json

JSON rather than TOML deliberately -- Anchor's core has zero required
dependencies (stdlib only, see README), and a TOML parser isn't in the
standard library before 3.11's read-only tomllib. json is universal and
this file is small enough that the format doesn't matter for readability.

Schema:
{
  "minimum_evidence": 1,
  "accepted": ["anchor_scan", "human_review"]
}

"accepted" restricts which evidence *types* count toward minimum_evidence --
e.g. a team that wants to disallow silent human_review-only commits would
set accepted = ["anchor_scan"] and minimum_evidence = 1, forcing every
change through anchor analyze regardless of what a person is willing to
self-certify.
"""

import json
import os
from typing import Any, Dict

DEFAULT_POLICY = {
    'minimum_evidence': 1,
    'accepted': ['anchor_scan', 'human_review'],
}


def _policy_path(project_root: str) -> str:
    return os.path.join(project_root, '.anchor', 'guardian_policy.json')


def load(project_root: str) -> Dict[str, Any]:
    path = _policy_path(project_root)
    if not os.path.exists(path):
        return dict(DEFAULT_POLICY)
    try:
        with open(path, 'r') as f:
            policy = json.load(f)
    except (json.JSONDecodeError, IOError):
        return dict(DEFAULT_POLICY)
    merged = dict(DEFAULT_POLICY)
    merged.update(policy)
    return merged


def save(project_root: str, policy: Dict[str, Any]) -> None:
    path = _policy_path(project_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(policy, f, indent=2)


def meets_policy(evidence_types: list, policy: Dict[str, Any]) -> bool:
    accepted = set(policy.get('accepted', DEFAULT_POLICY['accepted']))
    minimum = policy.get('minimum_evidence', DEFAULT_POLICY['minimum_evidence'])
    qualifying = [t for t in evidence_types if t in accepted]
    return len(qualifying) >= minimum

