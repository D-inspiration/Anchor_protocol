"""OpenAIAgent - Use an existing paid OpenAI API key as an Anchor-mediated agent.

For users who already pay for OpenAI and would rather spend that budget than
juggle a second free-tier key. Set OPENAI_API_KEY.
"""

import json
import os
import urllib.request
import urllib.error
from typing import Optional

from .base import AnchorAgent

DEFAULT_MODEL = 'gpt-4o-mini'
API_URL = 'https://api.openai.com/v1/chat/completions'


class OpenAIAPIError(RuntimeError):
    pass


class OpenAIAgent(AnchorAgent):
    provider_name = 'openai'

    def __init__(self, sidecar, api_key: Optional[str] = None, model: str = DEFAULT_MODEL,
                 actor_name: Optional[str] = None):
        super().__init__(sidecar, actor_name=actor_name or f'openai-{model}')
        self.api_key = api_key or os.environ.get('OPENAI_API_KEY')
        self.model = model

    def _call_llm(self, prompt: str, max_output_tokens: int = 1024) -> str:
        if not self.api_key:
            raise OpenAIAPIError("No OpenAI API key found. Set OPENAI_API_KEY or pass api_key= explicitly.")
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_output_tokens,
        }).encode('utf-8')
        req = urllib.request.Request(API_URL, data=body, headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}',
        }, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            raise OpenAIAPIError(f"OpenAI API error {e.code}: {e.read().decode('utf-8', 'ignore')}")
        except urllib.error.URLError as e:
            raise OpenAIAPIError(f"Could not reach OpenAI API: {e.reason}")

        try:
            return data['choices'][0]['message']['content']
        except (KeyError, IndexError):
            raise OpenAIAPIError(f"Unexpected OpenAI response shape: {data}")
