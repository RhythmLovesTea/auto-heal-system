from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class IssueType(str, Enum):
    stopped   = "stopped"
    crashed   = "crashed"
    dead      = "dead"
    unhealthy = "unhealthy"
    unknown   = "unknown"


class HealStatus(str, Enum):
    success  = "success"
    failed   = "failed"
    skipped  = "skipped"   # cooldown active or unknown issue type
    pending  = "pending"   # detected, heal not yet attempted


# ---------------------------------------------------------------------------
# Core schema
# ---------------------------------------------------------------------------

class Incident(BaseModel):
    container_name: str
    issue_type: IssueType
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Populated after heal attempt
    heal_status: HealStatus = HealStatus.pending
    healed_at: datetime | None = None
    restart_count: int = 0          # lifetime restarts for this container
    on_cooldown: bool = False
    error: str | None = None        # error message if heal failed

    def mark_healed(self, success: bool, restart_count: int, error: str | None = None) -> None:
        self.heal_status = HealStatus.success if success else HealStatus.failed
        self.healed_at = datetime.now(timezone.utc)
        self.restart_count = restart_count
        self.error = error

    def mark_skipped(self, reason: str | None = None) -> None:
        self.heal_status = HealStatus.skipped
        self.healed_at = datetime.now(timezone.utc)
        self.error = reason

    def to_log_dict(self) -> dict:
        """Serialise to a plain dict suitable for Redis storage / JSON responses."""
        return self.model_dump(mode="json")


# ---------------------------------------------------------------------------
# API response wrappers
# ---------------------------------------------------------------------------

class ScanResult(BaseModel):
    scanned_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    total_issues: int
    incidents: list[Incident]


class ContainerHistory(BaseModel):
    container_name: str
    restart_count: int
    incidents: list[Incident]
