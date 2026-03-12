from twilio.rest import Client

from core.config import get_settings
from core.models import BookingRecord
from core.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


async def send_booking_confirmation_sms(booking: BookingRecord) -> None:
    """Send booking confirmation SMS via Twilio."""
    if not booking.customer_phone:
        logger.info("sms_sender.skipped_no_phone", booking_id=booking.booking_id)
        return

    hour = int(booking.start_time.split(":")[0])
    am_pm = "AM" if hour < 12 else "PM"
    display_hour = hour if hour <= 12 else hour - 12

    body = (
        f"Booking Confirmed! ID: {booking.booking_id}. "
        f"{booking.service_type.upper()} on {booking.date} "
        f"at {display_hour}:00 {am_pm} with {booking.team_name}. "
        f"Reply CANCEL to cancel (24hr notice required)."
    )

    if settings.app_env.value == "development":
        logger.info(
            "sms_sender.dev_mode_skip",
            booking_id=booking.booking_id,
            to=booking.customer_phone,
            body=body,
        )
        return

    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    message = client.messages.create(
        body=body,
        from_=settings.twilio_phone_number,
        to=booking.customer_phone,
    )

    logger.info(
        "sms_sender.sent",
        booking_id=booking.booking_id,
        to=booking.customer_phone,
        message_sid=message.sid,
    )