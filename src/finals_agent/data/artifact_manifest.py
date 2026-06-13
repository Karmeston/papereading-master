from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from finals_agent.core.schemas import PaperArtifact, StudyDocument
from finals_agent.data.artifact_locator import ArtifactRegion, ArtifactRegionStore


MANIFEST_VERSION = 1


class ArtifactManifestStore:
    def read(
        self,
        document: StudyDocument,
    ) -> tuple[list[PaperArtifact], dict[str, ArtifactRegion]] | None:
        path = self.path(document)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("version") != MANIFEST_VERSION:
                return None
            if payload.get("fingerprint") != self.fingerprint(document):
                return None
            artifacts = [
                PaperArtifact.from_dict(item)
                for item in payload.get("artifacts", [])
                if isinstance(item, dict)
            ]
            regions = {
                region.artifact_id: region
                for region in (
                    ArtifactRegion.from_dict(item)
                    for item in payload.get("regions", [])
                    if isinstance(item, dict)
                )
            }
            return artifacts, regions
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None

    def write(
        self,
        document: StudyDocument,
        artifacts: list[PaperArtifact],
        regions: dict[str, ArtifactRegion],
    ) -> Path:
        path = self.path(document)
        temp = path.with_name(f".{path.name}.tmp")
        payload = {
            "version": MANIFEST_VERSION,
            "document_id": document.id,
            "fingerprint": self.fingerprint(document),
            "artifacts": [item.to_dict() for item in artifacts],
            "regions": [item.to_dict() for item in regions.values()],
        }
        temp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp.replace(path)
        return path

    def invalidate(self, document: StudyDocument) -> None:
        try:
            self.path(document).unlink(missing_ok=True)
        except OSError:
            return

    @staticmethod
    def path(document: StudyDocument) -> Path:
        return document.path.with_suffix(document.path.suffix + ".artifact_manifest.json")

    @staticmethod
    def fingerprint(document: StudyDocument) -> dict[str, Any]:
        paths = [
            document.path,
            document.path.with_suffix(document.path.suffix + ".artifacts.json"),
            ArtifactRegionStore.path(document),
        ]
        return {
            str(path.name): _stat_fingerprint(path)
            for path in paths
        }


def _stat_fingerprint(path: Path) -> dict[str, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
