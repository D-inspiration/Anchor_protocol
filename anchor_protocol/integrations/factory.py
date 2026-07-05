"""Agent factory - pick a provider without changing any code.

Resolution order (first match wins):
  1. `provider=` argument passed explicitly
  2. `ANCHOR_AGENT_PROVIDER` environment variable
  3. `.anchor/agent_config.json` (written by `anchor agent set-default`)
  4. 'gemini' (free tier, lowest friction default)

This is what makes "switch easily between Gemini free tier, a local Ollama
model, or a paid OpenAI/Anthropic key" a one-line change instead of a
re-integration. External agent frameworks (OpenHands, Openclaw, Cursor,
custom shell-based agents, etc.) don't need this at all -- they can just
shell out to the `anchor` CLI directly (see README "CLI-first" section) and
pass their own --actor name; this factory is for the Python-embedded path.
"""

import json
import os
from typing import Optional, Dict, Any

from .gemini_agent import GeminiAgent
from .ollama_agent import OllamaAgent
from .openai_agent import OpenAIAgent
from .anthropic_agent import AnthropicAgent

PROVIDERS = {
    'gemini': GeminiAgent,
    'ollama': OllamaAgent,
    'openai': OpenAIAgent,
    'anthropic': AnthropicAgent,
}

_ENV_VAR = 'ANCHOR_AGENT_PROVIDER'


def _config_path(project_root: str) -> str:
    return os.path.join(project_root, '.anchor', 'agent_config.json')


def _read_config(project_root: str) -> Dict[str, Any]:
    path = _config_path(project_root)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def set_default_provider(project_root: str, provider: str, **kwargs) -> None:
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider '{provider}'. Choices: {', '.join(PROVIDERS)}")
    path = _config_path(project_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    config = {'provider': provider, **kwargs}
    with open(path, 'w') as f:
        json.dump(config, f, indent=2)


def list_providers() -> Dict[str, str]:
    return {
        'gemini': 'Google Gemini free-tier API (GEMINI_API_KEY)',
        'ollama': 'Local models via Ollama, e.g. phi4, llama3 (no key, no internet)',
        'openai': 'Paid OpenAI API key (OPENAI_API_KEY)',
        'anthropic': 'Paid Anthropic API key (ANTHROPIC_API_KEY)',
    }


def get_agent(sidecar, provider: Optional[str] = None, **kwargs):
    """
    Resolve and instantiate an AnchorAgent subclass. Extra kwargs (model=,
    api_key=, host=, actor_name=) are forwarded to the provider's constructor.
    """
    config = _read_config(sidecar.project_root)
    resolved = provider or os.environ.get(_ENV_VAR) or config.get('provider') or 'gemini'

    if resolved not in PROVIDERS:
        raise ValueError(f"Unknown provider '{resolved}'. Choices: {', '.join(PROVIDERS)}")

    merged_kwargs = {k: v for k, v in config.items() if k != 'provider'}
    merged_kwargs.update(kwargs)  # explicit call-site kwargs win over saved config

    return PROVIDERS[resolved](sidecar, **merged_kwargs)
