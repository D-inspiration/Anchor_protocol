"""AnthropicAgent - Use an existing paid Anthropic API key as an Anchor-mediated agent.

Set ANTHROPIC_API_KEY. This is separate from the Claude Code / Claude.ai
subscription -- it's the same API-key path anyone building on the Anthropic
API already uses.
"""

import json
import os
import urllib.request
import urllib.error
from typing import Optional

from .base import AnchorAgent

DEFAULT_MODEL = 'claude-sonnet-4-6'
API_URL = 'https://api.anthropic.com/v1/messages'
API_VERSION = '2023-06-01'


class AnthropicAPIError(RuntimeError):
    pass


class AnthropicAgent(AnchorAgent):
    provider_name = 'anthropic'

    def __init__(self, sidecar, api_key: Optional[str] = None, model: str = DEFAULT_MODEL,
                 actor_name: Optional[str] = None):
        super().__init__(sidecar, actor_name=actor_name or f'anthropic-{model}')
        self.api_key = api_key or os.environ.get('ANTHROPIC_API_KEY')
        self.model = model

    def _call_llm(self, prompt: str, max_output_tokens: int = 1024) -> str:
        if not self.api_key:
            raise AnthropicAPIError("No Anthropic API key found. Set ANTHROPIC_API_KEY or pass api_key= explicitly.")
        body = json.dumps({
            "model": self.model,
            "max_tokens": max_output_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }).encode('utf-8')
        req = urllib.request.Request(API_URL, data=body, headers={
            'Content-Type': 'application/json',
            'x-api-key': self.api_key,
            'anthropic-version': API_VERSION,
        }, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            raise AnthropicAPIError(f"Anthropic API error {e.code}: {e.read().decode('utf-8', 'ignore')}")
        except urllib.error.URLError as e:
            raise AnthropicAPIError(f"Could not reach Anthropic API: {e.reason}")

        try:
            return data['content'][0]['text']
        except (KeyError, IndexError):
            raise AnthropicAPIError(f"Unexpected Anthropic response shape: {data}")
