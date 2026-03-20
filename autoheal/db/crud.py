from sqlalchemy.orm import Session

from autoheal.db.models import IncidentRecord
from autoheal.schemas.incident import Incident


def create_incident(db: Session, incident: Incident) -> IncidentRecord:
    record = IncidentRecord(
        container_name=incident.container_name,
        issue_type=incident.issue_type.value,
        heal_status=incident.heal_status.value,
        restart_count=incident.restart_count,
        on_cooldown=incident.on_cooldown,
        error=incident.error,
        detected_at=incident.detected_at,
        healed_at=incident.healed_at,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def update_incident(db: Session, record_id: int, incident: Incident) -> IncidentRecord | None:
    record = db.get(IncidentRecord, record_id)
    if not record:
        return None
    record.heal_status   = incident.heal_status.value
    record.restart_count = incident.restart_count
    record.on_cooldown   = incident.on_cooldown
    record.error         = incident.error
    record.healed_at     = incident.healed_at
    db.commit()
    db.refresh(record)
    return record


def get_incidents_for_container(
    db: Session, container_name: str, limit: int = 50
) -> list[IncidentRecord]:
    return (
        db.query(IncidentRecord)
        .filter(IncidentRecord.container_name == container_name)
        .order_by(IncidentRecord.detected_at.desc())
        .limit(limit)
        .all()
    )


def get_all_incidents(db: Session, limit: int = 100) -> list[IncidentRecord]:
    return (
        db.query(IncidentRecord)
        .order_by(IncidentRecord.detected_at.desc())
        .limit(limit)
        .all()
    )


def get_restart_count(db: Session, container_name: str) -> int:
    """Count total successful heals for a container from the DB."""
    return (
        db.query(IncidentRecord)
        .filter(
            IncidentRecord.container_name == container_name,
            IncidentRecord.heal_status == "success",
        )
        .count()
    )
