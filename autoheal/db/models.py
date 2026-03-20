from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from autoheal.db.database import Base


class IncidentRecord(Base):
    """Persistent record of every detected incident and its heal outcome."""
    __tablename__ = "incidents"

    id:             Mapped[int]  = mapped_column(Integer, primary_key=True, index=True)
    container_name: Mapped[str]  = mapped_column(String, index=True, nullable=False)
    issue_type:     Mapped[str]  = mapped_column(String, nullable=False)
    heal_status:    Mapped[str]  = mapped_column(String, default="pending")
    restart_count:  Mapped[int]  = mapped_column(Integer, default=0)
    on_cooldown:    Mapped[bool] = mapped_column(Boolean, default=False)
    error:          Mapped[str | None] = mapped_column(String, nullable=True)

    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    healed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
