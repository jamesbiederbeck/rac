"""
Storage adapter interface.

Per rsm_spec.md: "Storage adapters (YAML, SQLite, JSON, etc.) must
serialize to and from this model without changing its semantics." Every
adapter implements this interface and is otherwise free to choose its own
on-disk/on-wire representation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from rac.model import ResumeDocument


class StorageAdapter(ABC):
    @abstractmethod
    def load(self, path: Path) -> ResumeDocument:
        """Read a ResumeDocument from the given location."""

    @abstractmethod
    def save(self, document: ResumeDocument, path: Path) -> None:
        """Write a ResumeDocument to the given location."""
