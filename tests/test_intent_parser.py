import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from core.models import NormalizedMessage, Channel, Intent
from datetime import datetime


def make_message(text: str) -> NormalizedMessage:
    return NormalizedMessage(
        session_id="test-session-001",
        channel=Channel.CHAT,
        raw_text=text,
        customer_phone="+1234567890",
        timestamp=datetime.utcnow(),
    )


def test_normalized_message_creation():
    msg = make_message("Book an HVAC service")
    assert msg.session_id == "test-session-001"
    assert msg.channel == Channel.CHAT
    assert msg.raw_text == "Book an HVAC service"
    assert msg.customer_phone == "+1234567890"


def test_normalized_message_empty_text():
    msg = make_message("")
    assert msg.raw_text == ""


def test_normalized_message_channel_voice():
    msg = NormalizedMessage(
        session_id="CA123",
        channel=Channel.VOICE,
        raw_text="I need a plumber",
        timestamp=datetime.utcnow(),
    )
    assert msg.channel == Channel.VOICE
