from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class IngestionStatus(str, Enum):
    OK = "ok"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class SourceResult:
    source: str
    status: IngestionStatus
    records: int = 0
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    fetched_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "status": self.status.value,
            "records": self.records,
            "warnings": self.warnings,
            "error": self.error,
            "fetched_at": self.fetched_at,
        }


@dataclass
class IngestionResult:
    """Aggregated outcome from a data-ingestion stage."""

    sources: list[SourceResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def status(self) -> IngestionStatus:
        if not self.sources:
            return IngestionStatus.SKIPPED
        statuses = {s.status for s in self.sources}
        if IngestionStatus.FAILED in statuses and len(statuses) == 1:
            return IngestionStatus.FAILED
        if IngestionStatus.PARTIAL in statuses or (
            IngestionStatus.FAILED in statuses and len(statuses) > 1
        ):
            return IngestionStatus.PARTIAL
        return IngestionStatus.OK

    def add(self, result: SourceResult) -> None:
        self.sources.append(result)
        self.warnings.extend(result.warnings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "sources": [s.to_dict() for s in self.sources],
            "warnings": self.warnings,
        }
