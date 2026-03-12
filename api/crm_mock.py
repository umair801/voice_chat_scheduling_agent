from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
import uuid
import random

from core.models import TimeSlot, BookingRecord, BookingStatus, ServiceType
from core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/crm", tags=["CRM Mock"])

# ── In-memory store (replaced by Supabase in Step 11) ────────────────────────

_teams: list[dict] = [
    {"team_id": "team_001", "name": "Alpha Team",   "service_types": ["hvac", "electrical"], "capacity": 3},
    {"team_id": "team_002", "name": "Beta Team",    "service_types": ["plumbing", "general"], "capacity": 2},
    {"team_id": "team_003", "name": "Delta Team",   "service_types": ["cleaning", "pest_control", "landscaping"], "capacity": 4},
    {"team_id": "team_004", "name": "Gamma Team",   "service_types": ["hvac", "plumbing", "electrical"], "capacity": 3},
]

_bookings: dict[str, dict] = {}  # booking_id -> booking dict


# ── Request / Response Models ─────────────────────────────────────────────────

class CreateBookingRequest(BaseModel):
    session_id: str
    customer_name: str
    customer_phone: str
    customer_email: Optional[str] = None
    service_type: str
    team_id: str
    date: str           # "2025-01-15"
    start_time: str     # "14:00"
    end_time: str       # "15:00"
    notes: Optional[str] = None


class CancelBookingRequest(BaseModel):
    booking_id: str
    reason: Optional[str] = None


# ── Helper: generate slots for a team on a given date ────────────────────────

def _generate_slots(
    team: dict,
    date: str,
    duration_minutes: int,
) -> list[TimeSlot]:
    """Generate available time slots for a team on a given date."""
    slots: list[TimeSlot] = []
    business_hours = [8, 9, 10, 11, 13, 14, 15, 16]  # skip 12 (lunch)

    # Count existing bookings for this team on this date
    booked_times = {
        b["start_time"]
        for b in _bookings.values()
        if b["team_id"] == team["team_id"]
        and b["date"] == date
        and b["status"] != BookingStatus.CANCELLED
    }

    for hour in business_hours:
        start = f"{hour:02d}:00"
        end_hour = hour + max(1, duration_minutes // 60)
        end = f"{end_hour:02d}:00"

        # Slot is available if not already booked and random capacity check passes
        is_available = (
            start not in booked_times
            and random.random() > 0.15  # 85% base availability
        )

        slots.append(TimeSlot(
            slot_id=f"{team['team_id']}_{date}_{start}",
            team_id=team["team_id"],
            team_name=team["name"],
            date=date,
            start_time=start,
            end_time=end,
            available=is_available,
        ))

    return slots


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/teams")
async def get_teams() -> dict:
    """Return all available service teams."""
    logger.info("crm.get_teams", team_count=len(_teams))
    return {"teams": _teams, "total": len(_teams)}


@router.get("/availability")
async def get_availability(
    date: str = Query(..., description="ISO date string: 2025-01-15"),
    service_type: str = Query(..., description="Service type slug"),
    duration_minutes: int = Query(default=60, ge=30, le=480),
) -> dict:
    """
    Return available time slots for a given date and service type.
    Filters teams by service capability.
    """
    logger.info(
        "crm.get_availability",
        date=date,
        service_type=service_type,
        duration_minutes=duration_minutes,
    )

    # Validate date format
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be in YYYY-MM-DD format")

    # Filter teams that handle this service type
    capable_teams = [
        t for t in _teams
        if service_type.lower() in t["service_types"]
    ]

    if not capable_teams:
        logger.warning("crm.no_capable_teams", service_type=service_type)
        return {
            "date": date,
            "service_type": service_type,
            "slots": [],
            "has_availability": False,
            "message": f"No teams available for service type: {service_type}",
        }

    all_slots: list[dict] = []
    for team in capable_teams:
        team_slots = _generate_slots(team, date, duration_minutes)
        available = [s.model_dump() for s in team_slots if s.available]
        all_slots.extend(available)

    # Sort by time then team
    all_slots.sort(key=lambda s: (s["start_time"], s["team_id"]))

    logger.info(
        "crm.availability_result",
        date=date,
        total_slots=len(all_slots),
    )

    return {
        "date": date,
        "service_type": service_type,
        "slots": all_slots,
        "has_availability": len(all_slots) > 0,
        "total_available": len(all_slots),
    }


@router.post("/bookings", status_code=201)
async def create_booking(payload: CreateBookingRequest) -> dict:
    """Create a new booking in the CRM."""
    booking_id = f"BK-{uuid.uuid4().hex[:8].upper()}"

    booking = {
        "booking_id": booking_id,
        "session_id": payload.session_id,
        "customer_name": payload.customer_name,
        "customer_phone": payload.customer_phone,
        "customer_email": payload.customer_email,
        "service_type": payload.service_type,
        "team_id": payload.team_id,
        "date": payload.date,
        "start_time": payload.start_time,
        "end_time": payload.end_time,
        "notes": payload.notes,
        "status": BookingStatus.CONFIRMED,
        "created_at": datetime.utcnow().isoformat(),
    }

    _bookings[booking_id] = booking

    logger.info(
        "crm.booking_created",
        booking_id=booking_id,
        customer=payload.customer_name,
        date=payload.date,
        start_time=payload.start_time,
    )

    return {"booking": booking, "message": "Booking confirmed successfully"}


@router.get("/bookings/{customer_phone}")
async def get_bookings_by_phone(customer_phone: str) -> dict:
    """Retrieve all bookings for a customer by phone number."""
    customer_bookings = [
        b for b in _bookings.values()
        if b["customer_phone"] == customer_phone
    ]

    logger.info(
        "crm.get_bookings",
        customer_phone=customer_phone,
        found=len(customer_bookings),
    )

    return {
        "customer_phone": customer_phone,
        "bookings": customer_bookings,
        "total": len(customer_bookings),
    }


@router.patch("/bookings/{booking_id}/cancel")
async def cancel_booking(booking_id: str, payload: CancelBookingRequest) -> dict:
    """Cancel an existing booking."""
    if booking_id not in _bookings:
        raise HTTPException(status_code=404, detail=f"Booking {booking_id} not found")

    _bookings[booking_id]["status"] = BookingStatus.CANCELLED
    _bookings[booking_id]["cancellation_reason"] = payload.reason
    _bookings[booking_id]["cancelled_at"] = datetime.utcnow().isoformat()

    logger.info("crm.booking_cancelled", booking_id=booking_id, reason=payload.reason)

    return {
        "booking_id": booking_id,
        "status": "cancelled",
        "message": "Booking cancelled successfully",
    }


@router.get("/bookings")
async def list_all_bookings() -> dict:
    """List all bookings (admin/metrics use)."""
    return {
        "bookings": list(_bookings.values()),
        "total": len(_bookings),
    }