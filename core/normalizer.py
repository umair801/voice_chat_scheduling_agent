from datetime import datetime
import uuid

from core.models import NormalizedMessage, Channel
from core.logger import get_logger

logger = get_logger(__name__)


def normalize_voice_input(
    raw_text: str,
    call_sid: str,
    caller_number: str,
    metadata: dict | None = None,
) -> NormalizedMessage:
    """
    Normalize a Twilio voice transcription into a standard message object.
    session_id is the Twilio CallSid -- unique per call.
    """
    message = NormalizedMessage(
        session_id=call_sid,
        channel=Channel.VOICE,
        raw_text=raw_text.strip(),
        customer_phone=_clean_phone(caller_number),
        timestamp=datetime.utcnow(),
        metadata=metadata or {},
    )

    logger.info(
        "normalizer.voice_input",
        session_id=message.session_id,
        phone=message.customer_phone,
        text_length=len(message.raw_text),
    )

    return message


def normalize_chat_input(
    raw_text: str,
    channel: Channel,
    customer_phone: str | None = None,
    customer_email: str | None = None,
    customer_name: str | None = None,
    session_id: str | None = None,
    metadata: dict | None = None,
) -> NormalizedMessage:
    """
    Normalize a chat/SMS/WhatsApp message into a standard message object.
    Generates a new session_id if one is not provided.
    """
    resolved_session_id = session_id or _generate_session_id(channel, customer_phone)

    message = NormalizedMessage(
        session_id=resolved_session_id,
        channel=channel,
        raw_text=raw_text.strip(),
        customer_phone=_clean_phone(customer_phone) if customer_phone else None,
        customer_email=customer_email,
        customer_name=customer_name,
        timestamp=datetime.utcnow(),
        metadata=metadata or {},
    )

    logger.info(
        "normalizer.chat_input",
        session_id=message.session_id,
        channel=channel.value,
        phone=message.customer_phone,
        text_length=len(message.raw_text),
    )

    return message


def normalize_twilio_webhook(form_data: dict) -> NormalizedMessage:
    """
    Parse raw Twilio webhook POST form data into a NormalizedMessage.
    Handles both voice (SpeechResult) and SMS (Body) payloads.
    """
    call_sid = form_data.get("CallSid", "")
    message_sid = form_data.get("MessageSid", "")
    caller = form_data.get("From", "")
    body = form_data.get("Body", "")
    speech_result = form_data.get("SpeechResult", "")

    # Determine channel
    if call_sid:
        channel = Channel.VOICE
        text = speech_result or body
        session_id = call_sid
    elif message_sid:
        # Distinguish WhatsApp vs SMS by "From" prefix
        channel = Channel.WHATSAPP if caller.startswith("whatsapp:") else Channel.SMS
        text = body
        session_id = _generate_session_id(channel, caller)
    else:
        channel = Channel.CHAT
        text = body
        session_id = _generate_session_id(channel, caller)

    clean_phone = _clean_phone(caller)

    message = NormalizedMessage(
        session_id=session_id,
        channel=channel,
        raw_text=text.strip(),
        customer_phone=clean_phone,
        timestamp=datetime.utcnow(),
        metadata={
            "call_sid": call_sid,
            "message_sid": message_sid,
            "raw_from": caller,
        },
    )

    logger.info(
        "normalizer.twilio_webhook",
        session_id=message.session_id,
        channel=channel.value,
        has_text=bool(text.strip()),
    )

    return message


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean_phone(phone: str | None) -> str | None:
    """Strip whitespace and whatsapp: prefix from phone numbers."""
    if not phone:
        return None
    return phone.replace("whatsapp:", "").strip()


def _generate_session_id(channel: Channel, identifier: str | None) -> str:
    """
    Generate a deterministic session ID from channel + identifier.
    Falls back to a random UUID if no identifier is available.
    """
    if identifier:
        clean = identifier.replace("+", "").replace("-", "").replace(" ", "")
        return f"{channel.value}_{clean}"
    return f"{channel.value}_{uuid.uuid4().hex[:12]}"