"""Anchor Protocol - a zero-trust local governance sidecar for AI-assisted coding."""

__version__ = "0.2.0"

from .sidecar import AnchorSidecar, EditProposal, FileReadResult  # noqa: F401

__all__ = ["AnchorSidecar", "EditProposal", "FileReadResult", "__version__"]
