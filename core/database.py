from supabase import create_client, Client
from core.config import get_settings
from core.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

_client: Client | None = None


def get_db() -> Client:
    """Return a singleton Supabase client."""
    global _client
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_key)
        logger.info("database.connected", url=settings.supabase_url[:40])
    return _client


async def save_booking(booking_data: dict) -> dict | None:
    """Insert a booking record into Supabase."""
    try:
        db = get_db()
        result = db.table("bookings").insert(booking_data).execute()
        logger.info("database.booking_saved", booking_id=booking_data.get("booking_id"))
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error("database.save_booking_failed", error=str(e))
        return None


async def get_bookings_by_phone(phone: str) -> list[dict]:
    """Fetch all bookings for a customer by phone number."""
    try:
        db = get_db()
        result = (
            db.table("bookings")
            .select("*")
            .eq("customer_phone", phone)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []
    except Exception as e:
        logger.error("database.get_bookings_failed", error=str(e))
        return []


async def update_booking_status(booking_id: str, status: str, extra: dict | None = None) -> bool:
    """Update booking status (confirmed, cancelled, rescheduled)."""
    try:
        db = get_db()
        update_data = {"status": status, **(extra or {})}
        db.table("bookings").update(update_data).eq("booking_id", booking_id).execute()
        logger.info("database.booking_updated", booking_id=booking_id, status=status)
        return True
    except Exception as e:
        logger.error("database.update_booking_failed", error=str(e))
        return False


async def save_session(session_data: dict) -> bool:
    """Upsert session state."""
    try:
        db = get_db()
        db.table("sessions").upsert(session_data).execute()
        return True
    except Exception as e:
        logger.error("database.save_session_failed", error=str(e))
        return False


async def get_session(session_id: str) -> dict | None:
    """Retrieve session by ID."""
    try:
        db = get_db()
        result = (
            db.table("sessions")
            .select("*")
            .eq("session_id", session_id)
            .execute()
        )
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error("database.get_session_failed", error=str(e))
        return None


async def log_agent_event(
    session_id: str,
    event: str,
    channel: str | None = None,
    intent: str | None = None,
    booking_id: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Write an agent event to the logs table."""
    try:
        db = get_db()
        db.table("agent_logs").insert({
            "session_id": session_id,
            "event": event,
            "channel": channel,
            "intent": intent,
            "booking_id": booking_id,
            "metadata": metadata or {},
        }).execute()
    except Exception as e:
        logger.error("database.log_event_failed", error=str(e))