"""AnchorAgent - Provider-agnostic base for LLM-backed agents that act through Anchor.

The point of this abstraction: whichever model is actually doing the work
(Gemini free tier, a local Ollama model, a paid OpenAI/Anthropic key, or an
agent framework like OpenHands/Openclaw driving things externally), the
*governance* behavior is identical -- every write goes through
AnchorSidecar's Guardian-mediated propose_edit/execute_ticket, every agent
gets a stable actor_name for trust scoring, and every call is (optionally)
logged to local telemetry with the same event schema.

Concrete subclasses only need to implement `_call_llm(prompt) -> str`.
Everything else (explain_report, explain_blast_radius, propose_fix, response
cleanup, telemetry logging) is shared here so behavior can't drift between
providers.
"""

import json
import os
from typing import Optional, Dict, Any


class AnchorAgent:
    """Subclass and implement _call_llm(). Do not override the public methods
    unless a provider genuinely needs different mediation behavior."""

    provider_name = 'base'

    def __init__(self, sidecar, actor_name: Optional[str] = None):
        self.sidecar = sidecar
        self.actor_name = actor_name or f'{self.provider_name}-agent'
        self.telemetry = getattr(sidecar, 'telemetry', None)

    # -- override this in each provider --------------------------------

    def _call_llm(self, prompt: str, max_output_tokens: int = 1024) -> str:
        raise NotImplementedError

    # -- shared, provider-agnostic behavior -------------------------------

    def explain_report(self) -> str:
        report = self.sidecar.get_stability_report()
        prompt = (
            "You are reviewing a code stability report from a governance tool called Anchor. "
            "Summarize the key risks in 3-4 sentences, in plain language, for a developer "
            f"who has not seen this data yet:\n\n{json.dumps(report, default=str)[:6000]}"
        )
        explanation = self._call_llm(prompt)
        self._log('explain_report', {
            'agent': self.actor_name,
            'provider': self.provider_name,
            'drift_score': report.get('drift_score'),
            'drift_level': report.get('drift_level'),
        })
        return explanation

    def explain_blast_radius(self, symbol_name: str) -> str:
        radius = self.sidecar.blast_radius.compute(symbol_name)
        prompt = (
            f"A developer is about to change the function/symbol '{symbol_name}'. "
            f"Here is Anchor's blast-radius analysis:\n\n{json.dumps(radius, default=str)}\n\n"
            "In 2-3 sentences, explain the risk in plain language and whether they should get a second reviewer."
        )
        explanation = self._call_llm(prompt)
        self._log('explain_blast_radius', {
            'agent': self.actor_name,
            'provider': self.provider_name,
            'symbol': symbol_name,
            'risk': radius.get('risk'),
        })
        return explanation

    def propose_fix(self, rel_path: str, instruction: str) -> str:
        """
        Read `rel_path` (Guardian-mediated), ask the model for a full corrected
        file body per `instruction`, submit as an EditProposal. Returns a
        ticket id -- nothing is written to disk until execute_ticket() runs.
        """
        from ..sidecar import EditProposal

        current = self.sidecar.read_file(rel_path)
        prompt = (
            f"You are editing the file '{rel_path}'. Instruction: {instruction}\n\n"
            "Return ONLY the complete new file content, with no explanation, no markdown "
            "code fences, and no commentary before or after.\n\n--- CURRENT FILE ---\n"
            f"{current.content}"
        )
        new_content = self._strip_code_fences(self._call_llm(prompt, max_output_tokens=4096))

        proposal = EditProposal(
            path=rel_path, old_content=current.content, new_content=new_content,
            reason=instruction, actor=self.actor_name, confidence=0.7,
        )
        try:
            ticket = self.sidecar.propose_edit(proposal)
            self._log('propose_edit', {
                'agent': self.actor_name, 'provider': self.provider_name,
                'language': os.path.splitext(rel_path)[1].lstrip('.') or 'unknown',
                'accepted': True,
            })
            return ticket
        except PermissionError as e:
            self._log('propose_edit', {
                'agent': self.actor_name, 'provider': self.provider_name,
                'accepted': False, 'reason': str(e),
            })
            raise

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        stripped = text.strip()
        if stripped.startswith('```'):
            lines = stripped.splitlines()[1:]
            if lines and lines[-1].strip().startswith('```'):
                lines = lines[:-1]
            return '\n'.join(lines)
        return stripped

    def _log(self, event_type: str, payload: Dict[str, Any]) -> None:
        if self.telemetry is not None:
            self.telemetry.record_event(event_type, payload)
