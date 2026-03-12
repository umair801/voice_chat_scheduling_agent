# api/chat_router.py

import uuid
from typing import Optional

import structlog
from fastapi import APIRouter, Form, Request, Response
from fastapi.responses import JSONResponse
from twilio.twiml.messaging_response import MessagingResponse

from core.normalizer import normalize_chat_input, normalize_twilio_webhook
from core.orchestrator import run_agent
from core.session_manager import close_session, save_session_state
from core.models import Channel

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat"])


# ── Twilio WhatsApp / SMS Webhook ─────────────────────────────────────────────

@router.post("/webhook/twilio")
async def twilio_chat_webhook(
    request: Request,
    From: Optional[str] = Form(None),
    Body: Optional[str] = Form(None),
    MessageSid: Optional[str] = Form(None),
    To: Optional[str] = Form(None),
) -> Response:
    """
    Twilio webhook for inbound WhatsApp and SMS messages.

    Twilio sends a form-encoded POST for every inbound message.
    We detect WhatsApp vs SMS from the 'From' prefix, run the
    agent pipeline, and respond with TwiML MessagingResponse so
    Twilio delivers the reply back to the customer.
    """
    caller = From or "unknown"
    message_text = Body or ""
    message_sid = MessageSid or f"msg-{uuid.uuid4().hex[:8]}"

    # Detect channel from Twilio 'From' field
    if caller.startswith("whatsapp:"):
        channel = Channel.WHATSAPP
    else:
        channel = Channel.SMS

    log = logger.bind(channel=channel.value, from_=caller, message_sid=message_sid)
    log.info("twilio_chat_received", text_preview=message_text[:60])

    if not message_text.strip():
        reply = "Hello! I am your AI scheduling assistant. How can I help you today?"
        return _twilio_reply(reply)

    try:
        normalized = normalize_chat_input(
            raw_text=message_text,
            channel=channel,
            customer_phone=caller,
        )

        result = await run_agent(normalized)
        agent_reply: str = result.get("response_text", "")

        if not agent_reply:
            agent_reply = "I am sorry, I could not process that. Please try again."

        # Save session state
        await save_session_state(normalized.session_id, normalized, result)

        log.info("twilio_chat_reply_sent", reply_preview=agent_reply[:80])
        return _twilio_reply(agent_reply)

    except Exception as exc:
        log.error("twilio_chat_error", error=str(exc), exc_info=True)
        fallback = (
            "I am sorry, something went wrong. Please try again in a moment."
        )
        return _twilio_reply(fallback)


# ── Web Widget / API Webhook ──────────────────────────────────────────────────

@router.post("/webhook/web")
async def web_chat_webhook(request: Request) -> JSONResponse:
    """
    Web widget and direct API chat endpoint.

    Accepts JSON body with message, session_id, and optional customer info.
    Returns JSON with the agent reply and session_id for the frontend
    to persist across turns.

    Request body:
        {
            "message": "I need to book a plumbing appointment",
            "session_id": "optional-existing-session-id",
            "customer_phone": "+1234567890",
            "customer_email": "customer@example.com",
            "customer_name": "John Smith"
        }
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid JSON body."},
        )

    message_text: str = body.get("message", "").strip()
    session_id: Optional[str] = body.get("session_id")
    customer_phone: Optional[str] = body.get("customer_phone")
    customer_email: Optional[str] = body.get("customer_email")
    customer_name: Optional[str] = body.get("customer_name")

    log = logger.bind(session_id=session_id, channel="web")

    if not message_text:
        return JSONResponse(
            status_code=400,
            content={"error": "message field is required and cannot be empty."},
        )

    log.info("web_chat_received", text_preview=message_text[:60])

    try:
        normalized = normalize_chat_input(
            raw_text=message_text,
            channel=Channel.CHAT,
            customer_phone=customer_phone,
            customer_email=customer_email,
            customer_name=customer_name,
            session_id=session_id,
        )

        result = await run_agent(normalized)
        agent_reply: str = result.get("response_text", "")

        if not agent_reply:
            agent_reply = "I am sorry, I could not process that. Please try again."

        # Save session state for next turn
        await save_session_state(normalized.session_id, normalized, result)

        log.info(
            "web_chat_reply_sent",
            session_id=normalized.session_id,
            reply_preview=agent_reply[:80],
        )

        return JSONResponse(content={
            "reply": agent_reply,
            "session_id": normalized.session_id,
            "channel": Channel.CHAT.value,
        })

    except Exception as exc:
        log.error("web_chat_error", error=str(exc), exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error. Please try again.",
                "reply": "I am sorry, something went wrong on my end.",
            },
        )


# ── Session Close ─────────────────────────────────────────────────────────────

@router.post("/session/close")
async def close_chat_session(request: Request) -> JSONResponse:
    """
    Explicitly close a chat session when the customer ends the conversation.
    Called by the web widget on window close or disconnect.
    """
    try:
        body = await request.json()
        session_id: str = body.get("session_id", "")

        if not session_id:
            return JSONResponse(
                status_code=400,
                content={"error": "session_id is required."},
            )

        await close_session(session_id)
        logger.info("chat_session_closed", session_id=session_id)

        return JSONResponse(content={"status": "closed", "session_id": session_id})

    except Exception as exc:
        logger.error("session_close_error", error=str(exc))
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to close session."},
        )


# ── Health Check ──────────────────────────────────────────────────────────────

@router.get("/test")
async def chat_test_endpoint() -> dict:
    """
    Quick health check for the chat router.
    Verifies the router is wired correctly without sending a real message.
    """
    return {
        "status": "ok",
        "router": "chat",
        "endpoints": [
            "POST /chat/webhook/twilio  -- WhatsApp and SMS via Twilio",
            "POST /chat/webhook/web     -- Web widget and direct API",
            "POST /chat/session/close   -- Close a session explicitly",
        ],
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _twilio_reply(message: str) -> Response:
    """Build a Twilio MessagingResponse TwiML for WhatsApp/SMS replies."""
    resp = MessagingResponse()
    resp.message(message)
    return Response(content=str(resp), media_type="application/xml")