# api/voice_router.py

import uuid
from typing import Optional

import structlog
from fastapi import APIRouter, Form, Request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather

from core.normalizer import normalize_voice_input
from core.orchestrator import run_agent
from core.session_manager import close_session

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/voice", tags=["Voice"])


def _twiml_response(message: str, gather: bool = True) -> str:
    """
    Build a TwiML XML response.

    If gather=True, Twilio listens for the caller's next spoken input
    and POSTs it back to /voice/webhook -- keeps the conversation loop alive.
    If gather=False, Twilio reads the message and hangs up.
    """
    vr = VoiceResponse()

    if gather:
        g = Gather(
            input="speech",
            action="/voice/webhook",
            method="POST",
            speech_timeout="auto",
            language="en-US",
        )
        g.say(message, voice="Polly.Joanna", language="en-US")
        vr.append(g)

        # Fallback: if caller says nothing, close politely
        vr.say(
            "I did not hear anything. Please call back if you need assistance.",
            voice="Polly.Joanna",
        )
    else:
        vr.say(message, voice="Polly.Joanna", language="en-US")
        vr.hangup()

    return str(vr)


def _is_terminal_response(agent_reply: str) -> bool:
    """
    Detect whether the agent reply ends the conversation
    so Twilio can hang up instead of listening again.
    """
    terminal_phrases = [
        "your appointment is confirmed",
        "booking has been cancelled",
        "have a great day",
        "goodbye",
        "thank you for calling",
        "we will see you",
    ]
    lower = agent_reply.lower()
    return any(phrase in lower for phrase in terminal_phrases)


@router.post("/webhook")
async def voice_webhook(
    request: Request,
    CallSid: Optional[str] = Form(None),
    From: Optional[str] = Form(None),
    SpeechResult: Optional[str] = Form(None),
    CallStatus: Optional[str] = Form(None),
) -> Response:
    """
    Main Twilio Voice webhook.

    Twilio calls this endpoint at the start of every call and after
    every speech input. Flow:
      1. Extract call SID and transcribed speech (SpeechResult).
      2. Run agent pipeline with session state.
      3. Return TwiML that speaks the agent reply back to the caller.
    """
    call_sid = CallSid or f"test-{uuid.uuid4().hex[:8]}"
    caller_number = From or "unknown"
    speech_text = SpeechResult or ""

    log = logger.bind(call_sid=call_sid, caller=caller_number)
    log.info("voice_webhook_received", speech=speech_text, call_status=CallStatus)

    # --- Handle call-end status events from Twilio (no body needed) ---
    if CallStatus in ("completed", "busy", "no-answer", "failed", "canceled"):
        log.info("call_ended", status=CallStatus)
        await close_session(call_sid)
        return Response(content="", media_type="application/xml")

    # --- First turn: caller just connected, no speech yet ---
    if not speech_text:
        greeting = (
            "Hello! Thank you for calling. I am your AI scheduling assistant. "
            "How can I help you today? You can book an appointment, reschedule, "
            "or cancel an existing booking."
        )
        twiml = _twiml_response(greeting, gather=True)
        log.info("voice_greeting_sent")
        return Response(content=twiml, media_type="application/xml")

    # --- Subsequent turns: process speech through agent pipeline ---
    try:
        normalized = normalize_voice_input(
            raw_text=speech_text,
            call_sid=call_sid,
            caller_number=caller_number,
        )

        result = await run_agent(normalized)
        agent_reply: str = result.get("response_text", "")

        if not agent_reply:
            agent_reply = (
                "I am sorry, I could not process that. Could you please repeat?"
            )

        terminal = _is_terminal_response(agent_reply)
        twiml = _twiml_response(agent_reply, gather=not terminal)

        log.info(
            "voice_reply_sent",
            reply_preview=agent_reply[:80],
            terminal=terminal,
        )
        return Response(content=twiml, media_type="application/xml")

    except Exception as exc:
        log.error("voice_webhook_error", error=str(exc), exc_info=True)
        fallback = (
            "I am sorry, something went wrong on my end. "
            "Please try again or call back in a moment."
        )
        twiml = _twiml_response(fallback, gather=False)
        return Response(content=twiml, media_type="application/xml")


@router.post("/status")
async def voice_status_callback(
    CallSid: Optional[str] = Form(None),
    CallStatus: Optional[str] = Form(None),
) -> Response:
    """
    Twilio status callback endpoint.
    Twilio posts here when a call lifecycle changes (ringing, in-progress, completed).
    Used for logging and session cleanup only.
    """
    log = logger.bind(call_sid=CallSid)
    log.info("voice_status_callback", status=CallStatus)

    if CallStatus in ("completed", "failed", "busy", "no-answer"):
        if CallSid:
            await close_session(CallSid)
            log.info("session_cleaned_up", call_sid=CallSid)

    return Response(content="", media_type="application/xml")


@router.get("/test")
async def voice_test_endpoint() -> dict:
    """
    Quick health check for the voice router.
    Returns a sample TwiML greeting to verify the router is wired correctly
    without placing a real Twilio call.
    """
    sample_twiml = _twiml_response(
        "Voice router is online. Agent pipeline is ready.", gather=False
    )
    return {
        "status": "ok",
        "router": "voice",
        "sample_twiml": sample_twiml,
    }
