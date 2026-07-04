"""
YAML storage adapter (RSM-recommended default backend, project_plan.md).

On-disk layout: a single YAML file containing the flat entity lists
described in the RSM (person, organizations, positions, claims,
competencies, artifacts, evidence, credentials). Relationships are
expressed as id references between these lists — see rac.model for field
definitions (e.g. Position.organization_id, Claim.position_id).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from rac.model import ResumeDocument
from rac.storage.base import StorageAdapter


class YamlStorageAdapter(StorageAdapter):
    def load(self, path: Path) -> ResumeDocument:
        raw = yaml.safe_load(path.read_text()) or {}
        return ResumeDocument.model_validate(raw)

    def save(self, document: ResumeDocument, path: Path) -> None:
        data = document.model_dump(mode="json", exclude_none=True)
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
