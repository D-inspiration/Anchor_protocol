"""OllamaAgent - Local models (phi4, llama3, qwen, mistral, ...) as an Anchor-mediated agent.

No API key, no internet required once the model is pulled -- this is the
"AI governance without your code ever leaving the machine" path the README
leads with. Requires a running Ollama daemon (`ollama serve`, or the Termux
build) and a pulled model (`ollama pull phi4`).
"""

import json
import os
import urllib.request
import urllib.error
from typing import Optional

from .base import AnchorAgent

DEFAULT_MODEL = 'phi4'
DEFAULT_HOST = 'http://localhost:11434'


class OllamaAPIError(RuntimeError):
    pass


class OllamaAgent(AnchorAgent):
    provider_name = 'ollama'

    def __init__(self, sidecar, model: str = DEFAULT_MODEL, host: Optional[str] = None,
                 actor_name: Optional[str] = None):
        super().__init__(sidecar, actor_name=actor_name or f'ollama-{model}')
        self.model = model
        self.host = (host or os.environ.get('OLLAMA_HOST') or DEFAULT_HOST).rstrip('/')

    def _call_llm(self, prompt: str, max_output_tokens: int = 1024) -> str:
        url = f"{self.host}/api/generate"
        body = json.dumps({
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": max_output_tokens},
        }).encode('utf-8')
        req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'}, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            raise OllamaAPIError(f"Ollama error {e.code}: {e.read().decode('utf-8', 'ignore')}")
        except urllib.error.URLError as e:
            raise OllamaAPIError(
                f"Could not reach Ollama at {self.host} ({e.reason}). "
                f"Is `ollama serve` running and has `ollama pull {self.model}` been run?"
            )
        if 'response' not in data:
            raise OllamaAPIError(f"Unexpected Ollama response shape: {data}")
        return data['response']
