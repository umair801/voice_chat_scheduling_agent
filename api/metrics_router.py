# api/metrics_router.py

from datetime import datetime, timedelta
from typing import Optional

import structlog
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from core.database import get_db
from core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/metrics", tags=["Metrics"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _date_range(period: str) -> tuple[str, str]:
    """Return ISO start and end timestamps for a given period."""
    now = datetime.utcnow()
    if period == "daily":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "weekly":
        start = now - timedelta(days=now.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "monthly":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        start = now - timedelta(days=30)
    return start.isoformat(), now.isoformat()


def _safe_rate(numerator: int, denominator: int) -> float:
    """Return percentage rate, safe against zero division."""
    if denominator == 0:
        return 0.0
    return round((numerator / denominator) * 100, 2)


# ── Main Metrics Endpoint ─────────────────────────────────────────────────────

@router.get("/")
async def get_metrics(
    period: str = Query(
        default="monthly",
        description="Time period: daily, weekly, or monthly",
        pattern="^(daily|weekly|monthly)$",
    )
) -> JSONResponse:
    """
    Business KPI dashboard endpoint.

    Returns all key metrics that demonstrate the business value of the
    scheduling agent to enterprise clients.

    Metrics returned:
    - Booking volumes (total, confirmed, cancelled, rescheduled)
    - Booking completion rate
    - Average conversation turns to complete a booking
    - Voice vs chat channel split
    - Reschedule and cancellation rates
    - Team utilization rates
    - After-hours booking percentage
    """
    start_ts, end_ts = _date_range(period)
    log = logger.bind(period=period, start=start_ts, end=end_ts)
    log.info("metrics.request")

    try:
        supabase = get_db()

        # ── Booking volume metrics ────────────────────────────────────────────
        all_bookings_resp = (
            supabase.table("bookings")
            .select("*")
            .gte("created_at", start_ts)
            .lte("created_at", end_ts)
            .execute()
        )
        all_bookings: list[dict] = all_bookings_resp.data or []
        total_bookings = len(all_bookings)

        confirmed = sum(1 for b in all_bookings if b.get("status") == "confirmed")
        cancelled = sum(1 for b in all_bookings if b.get("status") == "cancelled")
        rescheduled = sum(1 for b in all_bookings if b.get("status") == "rescheduled")
        pending = total_bookings - confirmed - cancelled - rescheduled

        # ── Channel split ─────────────────────────────────────────────────────
        voice_bookings = sum(1 for b in all_bookings if b.get("channel") == "voice")
        chat_bookings = total_bookings - voice_bookings

        # ── After-hours bookings (before 8am or after 6pm) ────────────────────
        after_hours = 0
        for b in all_bookings:
            raw_time = b.get("scheduled_time", "")
            if raw_time:
                try:
                    dt = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
                    hour = dt.hour
                    if hour < 8 or hour >= 18:
                        after_hours += 1
                except Exception:
                    pass

        # ── Session / conversation metrics ────────────────────────────────────
        sessions_resp = (
            supabase.table("sessions")
            .select("turn_count, channel, is_active")
            .gte("created_at", start_ts)
            .lte("created_at", end_ts)
            .execute()
        )
        sessions: list[dict] = sessions_resp.data or []
        total_sessions = len(sessions)

        turn_counts = [
            s.get("turn_count", 0)
            for s in sessions
            if s.get("turn_count", 0) > 0
        ]
        avg_turns = (
            round(sum(turn_counts) / len(turn_counts), 2) if turn_counts else 0.0
        )

        # ── Team utilization ──────────────────────────────────────────────────
        teams_resp = supabase.table("teams").select("*").execute()
        teams: list[dict] = teams_resp.data or []

        team_utilization = []
        for team in teams:
            team_id = team.get("id")
            team_bookings = sum(
                1 for b in all_bookings if b.get("team_id") == team_id
            )
            team_utilization.append({
                "team_id": team_id,
                "team_name": team.get("name", "Unknown"),
                "service_type": team.get("service_type", ""),
                "bookings_in_period": team_bookings,
                "utilization_rate_pct": _safe_rate(team_bookings, total_bookings),
            })

        # Sort by most utilized
        team_utilization.sort(
            key=lambda x: x["bookings_in_period"], reverse=True
        )

        # ── Service type breakdown ────────────────────────────────────────────
        service_counts: dict[str, int] = {}
        for b in all_bookings:
            svc = b.get("service_type", "unknown")
            service_counts[svc] = service_counts.get(svc, 0) + 1

        service_breakdown = [
            {
                "service_type": svc,
                "count": count,
                "share_pct": _safe_rate(count, total_bookings),
            }
            for svc, count in sorted(
                service_counts.items(), key=lambda x: x[1], reverse=True
            )
        ]

        # ── Assemble response ─────────────────────────────────────────────────
        metrics = {
            "period": period,
            "generated_at": datetime.utcnow().isoformat(),
            "range": {"start": start_ts, "end": end_ts},

            "booking_volume": {
                "total": total_bookings,
                "confirmed": confirmed,
                "cancelled": cancelled,
                "rescheduled": rescheduled,
                "pending": pending,
            },

            "rates": {
                "completion_rate_pct": _safe_rate(confirmed, total_bookings),
                "cancellation_rate_pct": _safe_rate(cancelled, total_bookings),
                "reschedule_rate_pct": _safe_rate(rescheduled, total_bookings),
                "after_hours_pct": _safe_rate(after_hours, total_bookings),
            },

            "conversation": {
                "total_sessions": total_sessions,
                "avg_turns_to_complete": avg_turns,
            },

            "channels": {
                "voice": voice_bookings,
                "chat": chat_bookings,
                "voice_share_pct": _safe_rate(voice_bookings, total_bookings),
                "chat_share_pct": _safe_rate(chat_bookings, total_bookings),
            },

            "team_utilization": team_utilization,
            "service_breakdown": service_breakdown,

            "business_impact": {
                "note": (
                    "Baseline: 8-15 min manual booking. "
                    "Agent target: under 2 min. "
                    "Staff hours saved estimated at 90% reduction."
                ),
                "after_hours_bookings": after_hours,
                "after_hours_coverage_pct": 100,
            },
        }

        log.info("metrics.response_built", total_bookings=total_bookings)
        return JSONResponse(content=metrics)

    except Exception as exc:
        log.error("metrics.error", error=str(exc), exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to retrieve metrics.", "detail": str(exc)},
        )


# ── Health Check ──────────────────────────────────────────────────────────────

@router.get("/health")
async def metrics_health() -> dict:
    """Confirm the metrics router is reachable."""
    return {
        "status": "ok",
        "router": "metrics",
        "available_periods": ["daily", "weekly", "monthly"],
    }