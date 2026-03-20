from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from autoheal.db.database import get_db
from autoheal.db import crud
from autoheal.schemas.incident import IncidentOut

# ─── ROUTER ──────────────────────────────────────────────────────────────────
# This router is registered in main.py with prefix "/incidents"
# So a function decorated @router.get("/") is reachable at GET /incidents/
router = APIRouter()


# ─── GET /incidents ───────────────────────────────────────────────────────────
# Returns a list of incidents. Dashboard calls this on first load to fill the
# timeline with historical data before SSE starts pushing new events.
#
# Query params:
#   ?limit=20          → how many to return (default 20, max 100)
#   ?service=payments-api  → filter by service name (optional)
#   ?status=resolved   → filter by status (optional)
@router.get("/", response_model=List[IncidentOut])
def list_incidents(
    limit:   int            = Query(default=20, le=100),
    service: Optional[str] = Query(default=None),
    status:  Optional[str] = Query(default=None),
    db:      Session        = Depends(get_db),
):
    """
    Fetch incident history.
    The dashboard calls this once on mount to pre-populate the timeline.
    """
    incidents = crud.get_incidents(db, limit=limit, service=service, status=status)
    return incidents


# ─── GET /incidents/{incident_id} ────────────────────────────────────────────
# Returns a single incident by its ID.
# Useful for the dashboard if you later add a "click to expand" detail view.
@router.get("/{incident_id}", response_model=IncidentOut)
def get_incident(incident_id: int, db: Session = Depends(get_db)):
    """
    Fetch one incident by ID.
    Returns 404 if not found.
    """
    incident = crud.get_incident_by_id(db, incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


# ─── GET /incidents/stats/summary ────────────────────────────────────────────
# Returns aggregate stats — used by the Stats panel in the dashboard.
# Example response:
#   { "total": 7, "healed": 5, "active": 2, "avg_heal_time": 23 }
@router.get("/stats/summary")
def get_stats(db: Session = Depends(get_db)):
    """
    Returns summary stats for the Stats panel on the dashboard.
    Called once on mount alongside /incidents.
    """
    stats = crud.get_incident_stats(db)
    return stats
