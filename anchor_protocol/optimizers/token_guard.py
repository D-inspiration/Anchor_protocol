"""TokenGuard - Budget management for Gemini free tier."""

from typing import Dict


class TokenGuard:
    def __init__(self, daily_budget: int = 1_000_000):
        self.daily_budget = daily_budget
        self.read_budget = int(daily_budget * 0.6)
        self.edit_budget = int(daily_budget * 0.4)
        self.read_used = 0
        self.edit_used = 0
        self.read_cache: Dict[str, int] = {}

    def reset(self):
        self.read_used = 0
        self.edit_used = 0
        self.read_cache.clear()

    def _estimate_tokens(self, content_length: int) -> int:
        return content_length // 4

    def check_read_budget(self, path: str):
        if path in self.read_cache:
            return
        remaining = self.read_budget - self.read_used
        if remaining < 1000:
            raise RuntimeError(f"Token budget exhausted: {self.read_used}/{self.read_budget} tokens used. Reset session or wait for daily reset.")

    def record_read(self, path: str, content_length: int):
        tokens = self._estimate_tokens(content_length)
        self.read_used += tokens
        self.read_cache[path] = tokens

    def check_edit_budget(self, path: str, new_content_length: int):
        tokens = self._estimate_tokens(new_content_length)
        remaining = self.edit_budget - self.edit_used
        if tokens > remaining:
            raise RuntimeError(f"Edit exceeds remaining budget: needs {tokens}, has {remaining}. Consider smaller edits or reset session.")

    def record_edit(self, path: str, content_length: int):
        tokens = self._estimate_tokens(content_length)
        self.edit_used += tokens

    def get_status(self) -> Dict:
        total_used = self.read_used + self.edit_used
        return {
            'daily_budget': self.daily_budget,
            'total_used': total_used,
            'total_remaining': self.daily_budget - total_used,
            'read_used': self.read_used,
            'read_budget': self.read_budget,
            'read_remaining': self.read_budget - self.read_used,
            'edit_used': self.edit_used,
            'edit_budget': self.edit_budget,
            'edit_remaining': self.edit_budget - self.edit_used,
            'percent_used': round(total_used / self.daily_budget * 100, 1),
            'cached_files': len(self.read_cache)
        }