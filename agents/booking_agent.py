import uuid
import httpx

from core.config import get_settings
from core.models import (
    BookingRecord,
    BookingRequest,
    BookingStatus,
    TimeSlot,
    NormalizedMessage,
)
from core.logger import get_logger
from notifications.email_sender import send_booking_confirmation_email
from notifications.sms_sender import send_booking_confirmation_sms

logger = get_logger(__name__)
settings = get_settings()


async def confirm_booking(
    request: BookingRequest,
    session_id: str,
) -> tuple[BookingRecord | None, str]:
    """
    Write booking to CRM, send notifications, return BookingRecord and response text.
    Returns (None, error_message) on failure.
    """
    logger.info(
        "booking_agent.start",
        session_id=session_id,
        customer=request.customer_name,
        date=request.slot.date,
        start_time=request.slot.start_time,
        service_type=request.service_type.value,
    )

    try:
        # Step 1: Write to CRM
        booking = await _post_to_crm(request)

        # Step 2: Send customer notifications (non-blocking failures)
        await _send_notifications(booking)

        response_text = _build_confirmation_response(booking)

        logger.info(
            "booking_agent.success",
            session_id=session_id,
            booking_id=booking.booking_id,
        )

        return booking, response_text

    except httpx.HTTPStatusError as e:
        error = f"CRM error {e.response.status_code}: {e.response.text}"
        logger.error("booking_agent.crm_error", session_id=session_id, error=error)
        return None, _build_failure_response()

    except Exception as e:
        logger.error("booking_agent.failed", session_id=session_id, error=str(e))
        return None, _build_failure_response()


async def _post_to_crm(request: BookingRequest) -> BookingRecord:
    """POST booking to CRM and return a BookingRecord."""
    payload = {
        "session_id": request.session_id,
        "customer_name": request.customer_name,
        "customer_phone": request.customer_phone,
        "customer_email": request.customer_email,
        "service_type": request.service_type.value,
        "team_id": request.slot.team_id,
        "date": request.slot.date,
        "start_time": request.slot.start_time,
        "end_time": request.slot.end_time,
        "notes": request.notes,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.crm_base_url}/bookings",
            json=payload,
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()

    b = data["booking"]
    return BookingRecord(
        booking_id=b["booking_id"],
        session_id=b["session_id"],
        customer_name=b["customer_name"],
        customer_phone=b["customer_phone"],
        customer_email=b.get("customer_email"),
        service_type=b["service_type"],
        team_id=b["team_id"],
        team_name=request.slot.team_name,
        date=b["date"],
        start_time=b["start_time"],
        end_time=b["end_time"],
        status=BookingStatus.CONFIRMED,
        notes=b.get("notes"),
    )


async def _send_notifications(booking: BookingRecord) -> None:
    """Send email and SMS notifications. Log but never crash on failure."""
    # Email notification
    if booking.customer_email:
        try:
            await send_booking_confirmation_email(booking)
        except Exception as e:
            logger.warning(
                "booking_agent.email_failed",
                booking_id=booking.booking_id,
                error=str(e),
            )

    # SMS notification
    if booking.customer_phone:
        try:
            await send_booking_confirmation_sms(booking)
        except Exception as e:
            logger.warning(
                "booking_agent.sms_failed",
                booking_id=booking.booking_id,
                error=str(e),
            )


def _build_confirmation_response(booking: BookingRecord) -> str:
    hour = int(booking.start_time.split(":")[0])
    am_pm = "AM" if hour < 12 else "PM"
    display_hour = hour if hour <= 12 else hour - 12

    return (
        f"Your {booking.service_type.upper()} appointment is confirmed. "
        f"Booking ID: {booking.booking_id}. "
        f"Date: {booking.date} at {display_hour}:00 {am_pm} "
        f"with {booking.team_name}. "
        f"You will receive a confirmation message shortly. "
        f"Is there anything else I can help you with?"
    )


def _build_failure_response() -> str:
    return (
        "I'm sorry, I was unable to complete your booking at this time. "
        "Please try again or call us directly to schedule your appointment."
    )