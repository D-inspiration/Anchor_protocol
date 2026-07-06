"""GeminiAgent - Google's free-tier Gemini API as an Anchor-mediated agent.

Get a free-tier key at https://aistudio.google.com/apikey and set
GEMINI_API_KEY (or GOOGLE_API_KEY). No paid plan required for light usage.
See integrations/base.py for what "Anchor-mediated" means.
"""

import json
import os
import urllib.request
import urllib.error
from typing import Optional

from .base import AnchorAgent

DEFAULT_MODEL = 'gemini-3.1-flash-lite'
API_BASE = 'https://generativelanguage.googleapis.com/v1beta/models'


class GeminiAPIError(RuntimeError):
    pass


class GeminiAgent(AnchorAgent):
    provider_name = 'gemini'

    def __init__(self, sidecar, api_key: Optional[str] = None, model: str = DEFAULT_MODEL,
                 actor_name: Optional[str] = None, thinking_level: str = 'low'):
        default_actor = model if model.startswith('gemini') else f'gemini-{model}'
        super().__init__(sidecar, actor_name=actor_name or default_actor)
        self.api_key = api_key or os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')
        self.model = model
        # Gemini 3.x defaults to thinking_level="high" if unset, which costs more
        # tokens/time than a simple bulk edit or classification needs. 'low' is a
        # sane default for propose_fix/explain calls; pass thinking_level='high'
        # explicitly if you want deeper reasoning on a specific call.
        self.thinking_level = thinking_level

    def _call_llm(self, prompt: str, max_output_tokens: int = 1024) -> str:
        if not self.api_key:
            raise GeminiAPIError(
                "No Gemini API key found. Set GEMINI_API_KEY (free tier: "
                "https://aistudio.google.com/apikey) or pass api_key= explicitly."
            )
        url = f"{API_BASE}/{self.model}:generateContent?key={self.api_key}"
        body = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": max_output_tokens,
                "thinkingConfig": {"thinkingLevel": self.thinking_level},
            },
        }).encode('utf-8')
        req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'}, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            raise GeminiAPIError(f"Gemini API error {e.code}: {e.read().decode('utf-8', 'ignore')}")
        except urllib.error.URLError as e:
            raise GeminiAPIError(f"Could not reach Gemini API: {e.reason}")

        try:
            return data['candidates'][0]['content']['parts'][0]['text']
        except (KeyError, IndexError):
            raise GeminiAPIError(f"Unexpected Gemini response shape: {data}")
