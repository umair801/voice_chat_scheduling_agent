import httpx
from datetime import datetime, timedelta

from core.config import get_settings
from core.models import BookingRecord, BookingStatus
from core.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


async def lookup_bookings(
    customer_phone: str,
    session_id: str,
) -> tuple[list[BookingRecord], str]:
    """
    Look up all active bookings for a customer by phone number.
    Returns (bookings_list, response_text).
    """
    logger.info(
        "cancellation_agent.lookup",
        session_id=session_id,
        customer_phone=customer_phone,
    )

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.crm_base_url}/bookings/{customer_phone}",
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()

        all_bookings = []
        for b in data.get("bookings", []):
            if "team_name" not in b or not b["team_name"]:
                b["team_name"] = b.get("team_id", "Assigned Team")
            all_bookings.append(BookingRecord(**b))

        # Filter to only active bookings
        active = [
            b for b in all_bookings
            if b.status == BookingStatus.CONFIRMED
        ]

        logger.info(
            "cancellation_agent.lookup_result",
            session_id=session_id,
            total=len(all_bookings),
            active=len(active),
        )

        if not active:
            return [], "I could not find any active bookings for your phone number. Would you like to schedule a new appointment?"

        response_text = _build_bookings_list_response(active)
        return active, response_text

    except httpx.HTTPStatusError as e:
        logger.error(
            "cancellation_agent.lookup_http_error",
            session_id=session_id,
            status_code=e.response.status_code,
        )
        return [], "I was unable to retrieve your bookings at this time. Please try again."

    except Exception as e:
        logger.error(
            "cancellation_agent.lookup_failed",
            session_id=session_id,
            error=str(e),
        )
        return [], "I was unable to retrieve your bookings at this time. Please try again."


async def cancel_booking(
    booking: BookingRecord,
    session_id: str,
    reason: str | None = None,
) -> tuple[bool, str]:
    """
    Cancel a booking after checking the cancellation policy window.
    Returns (success, response_text).
    """
    logger.info(
        "cancellation_agent.cancel_start",
        session_id=session_id,
        booking_id=booking.booking_id,
    )

    # Check cancellation policy window
    policy_check, policy_message = _check_cancellation_policy(booking)
    if not policy_check:
        logger.warning(
            "cancellation_agent.policy_violation",
            session_id=session_id,
            booking_id=booking.booking_id,
        )
        return False, policy_message

    try:
        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{settings.crm_base_url}/bookings/{booking.booking_id}/cancel",
                json={"booking_id": booking.booking_id, "reason": reason},
                timeout=10.0,
            )
            response.raise_for_status()

        logger.info(
            "cancellation_agent.cancelled",
            session_id=session_id,
            booking_id=booking.booking_id,
        )

        return True, _build_cancellation_response(booking)

    except Exception as e:
        logger.error(
            "cancellation_agent.cancel_failed",
            session_id=session_id,
            booking_id=booking.booking_id,
            error=str(e),
        )
        return False, "I was unable to cancel your booking at this time. Please call us directly."


def prepare_reschedule(booking: BookingRecord) -> tuple[str, str]:
    """
    Prepare a reschedule by returning the service type and a prompt.
    The orchestrator will re-enter the booking flow with this context.
    Returns (service_type_value, response_text).
    """
    logger.info(
        "cancellation_agent.reschedule_prepare",
        booking_id=booking.booking_id,
        service_type=booking.service_type,
    )

    response_text = (
        f"I will cancel your current {booking.service_type.upper()} appointment "
        f"on {booking.date} and help you find a new time. "
        f"What date and time works best for you?"
    )

    return booking.service_type, response_text


def select_booking_from_list(
    bookings: list[BookingRecord],
    customer_choice: str,
) -> BookingRecord | None:
    """
    Match customer's choice to a booking from the list.
    Handles ordinal words, booking IDs, and date mentions.
    """
    choice = customer_choice.lower().strip()

    ordinal_map = {
        "first": 0, "1st": 0, "1": 0, "one": 0,
        "second": 1, "2nd": 1, "2": 1, "two": 1,
        "third": 2, "3rd": 2, "3": 2, "three": 2,
    }

    if choice in ordinal_map:
        idx = ordinal_map[choice]
        if idx < len(bookings):
            return bookings[idx]

    # Match by booking ID
    for booking in bookings:
        if booking.booking_id.lower() in choice:
            return booking

    # Match by date mention
    for booking in bookings:
        if booking.date in choice:
            return booking

    return None


# ── Policy and Response Helpers ───────────────────────────────────────────────

def _check_cancellation_policy(booking: BookingRecord) -> tuple[bool, str]:
    """
    Check if booking can be cancelled within the policy window.
    Default: must cancel at least 24 hours before appointment.
    """
    try:
        appointment_dt = datetime.strptime(
            f"{booking.date} {booking.start_time}", "%Y-%m-%d %H:%M"
        )
        hours_until = (appointment_dt - datetime.utcnow()).total_seconds() / 3600

        if hours_until < settings.cancellation_window_hours:
            return False, (
                f"I'm sorry, cancellations require at least "
                f"{settings.cancellation_window_hours} hours notice. "
                f"Your appointment is in {int(hours_until)} hours. "
                f"Please call us directly to discuss your options."
            )
        return True, ""

    except ValueError:
        # If date parsing fails, allow cancellation
        return True, ""


def _build_bookings_list_response(bookings: list[BookingRecord]) -> str:
    lines = ["I found the following active bookings for your account:"]
    for i, b in enumerate(bookings, 1):
        hour = int(b.start_time.split(":")[0])
        am_pm = "AM" if hour < 12 else "PM"
        display_hour = hour if hour <= 12 else hour - 12
        lines.append(
            f"Booking {i}: {b.service_type.upper()} on {b.date} "
            f"at {display_hour}:00 {am_pm} with {b.team_name}. "
            f"ID: {b.booking_id}"
        )
    lines.append("Which booking would you like to cancel or reschedule?")
    return "\n".join(lines)


def _build_cancellation_response(booking: BookingRecord) -> str:
    return (
        f"Your {booking.service_type.upper()} appointment on {booking.date} "
        f"has been successfully cancelled. Booking ID: {booking.booking_id}. "
        f"Would you like to schedule a new appointment?"
    )