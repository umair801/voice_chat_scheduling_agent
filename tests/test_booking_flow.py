import pytest
from core.models import Channel, NormalizedMessage
from core.normalizer import normalize_chat_input, normalize_voice_input


def test_normalize_chat_input():
    msg = normalize_chat_input(
        raw_text="Book a plumbing appointment",
        channel=Channel.CHAT,
        customer_phone="+1234567890",
        customer_email="john@example.com",
        customer_name="John Smith",
    )
    assert msg.channel == Channel.CHAT
    assert msg.raw_text == "Book a plumbing appointment"
    assert msg.customer_phone == "+1234567890"
    assert msg.session_id is not None


def test_normalize_voice_input():
    msg = normalize_voice_input(
        raw_text="I need to schedule an HVAC service",
        call_sid="CA1234567890abcdef",
        caller_number="+1987654321",
    )
    assert msg.channel == Channel.VOICE
    assert msg.session_id == "CA1234567890abcdef"
    assert msg.customer_phone == "+1987654321"


def test_normalize_strips_whitespace():
    msg = normalize_chat_input(
        raw_text="   Book appointment   ",
        channel=Channel.SMS,
        customer_phone="+1234567890",
    )
    assert msg.raw_text == "Book appointment"


def test_normalize_whatsapp_strips_prefix():
    msg = normalize_chat_input(
        raw_text="Cancel my booking",
        channel=Channel.WHATSAPP,
        customer_phone="whatsapp:+1234567890",
    )
    assert msg.customer_phone == "+1234567890"


def test_session_id_generated_when_not_provided():
    msg = normalize_chat_input(
        raw_text="Hello",
        channel=Channel.CHAT,
        customer_phone="+1234567890",
    )
    assert msg.session_id.startswith("chat_")
