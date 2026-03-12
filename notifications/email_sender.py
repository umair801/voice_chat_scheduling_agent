import sendgrid
from sendgrid.helpers.mail import Mail

from core.config import get_settings
from core.models import BookingRecord
from core.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


async def send_booking_confirmation_email(booking: BookingRecord) -> None:
    """Send booking confirmation email via SendGrid."""
    if not booking.customer_email:
        logger.info("email_sender.skipped_no_email", booking_id=booking.booking_id)
        return

    hour = int(booking.start_time.split(":")[0])
    am_pm = "AM" if hour < 12 else "PM"
    display_hour = hour if hour <= 12 else hour - 12

    html_content = f"""
    <h2>Appointment Confirmed</h2>
    <p>Dear {booking.customer_name},</p>
    <p>Your appointment has been successfully scheduled.</p>
    <table>
        <tr><td><strong>Booking ID:</strong></td><td>{booking.booking_id}</td></tr>
        <tr><td><strong>Service:</strong></td><td>{booking.service_type.upper()}</td></tr>
        <tr><td><strong>Date:</strong></td><td>{booking.date}</td></tr>
        <tr><td><strong>Time:</strong></td><td>{display_hour}:00 {am_pm}</td></tr>
        <tr><td><strong>Team:</strong></td><td>{booking.team_name}</td></tr>
    </table>
    <p>If you need to reschedule or cancel, please contact us at least 24 hours in advance.</p>
    """

    message = Mail(
        from_email=settings.from_email,
        to_emails=booking.customer_email,
        subject=f"Appointment Confirmed - {booking.date} at {display_hour}:00 {am_pm}",
        html_content=html_content,
    )

    if settings.app_env.value == "development":
        logger.info(
            "email_sender.dev_mode_skip",
            booking_id=booking.booking_id,
            to=booking.customer_email,
            subject=message.subject,
        )
        return

    sg = sendgrid.SendGridAPIClient(api_key=settings.sendgrid_api_key)
    response = sg.send(message)

    logger.info(
        "email_sender.sent",
        booking_id=booking.booking_id,
        to=booking.customer_email,
        status_code=response.status_code,
    )