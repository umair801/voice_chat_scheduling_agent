from typing import Literal
from langgraph.graph import StateGraph, END
from pydantic import BaseModel
from typing import Optional

from core.models import (
    AgentState,
    Intent,
    NormalizedMessage,
    BookingRequest,
    ServiceType,
)
from core.config import get_settings
from core.logger import get_logger
from agents.intent_parser import parse_intent
from agents.availability_agent import check_availability
from agents.conflict_resolver import (
    resolve_conflict,
    select_slot_from_alternatives,
    build_confirmation_prompt,
)
from agents.booking_agent import confirm_booking
from agents.cancellation_agent import (
    lookup_bookings,
    cancel_booking,
    prepare_reschedule,
    select_booking_from_list,
)

logger = get_logger(__name__)
settings = get_settings()


# ── Node Functions ────────────────────────────────────────────────────────────

async def node_parse_intent(state: dict) -> dict:
    """Node 1: Parse intent from normalized message."""
    message: NormalizedMessage = state["message"]

    logger.info("orchestrator.node_parse_intent", session_id=message.session_id)

    parsed = await parse_intent(message)
    state["parsed_intent"] = parsed
    state["turn_count"] = state.get("turn_count", 0) + 1

    # Append to conversation history
    history = state.get("conversation_history", [])
    history.append({"role": "user", "content": message.raw_text})
    state["conversation_history"] = history

    return state


async def node_check_availability(state: dict) -> dict:
    """Node 2: Check CRM availability."""
    message: NormalizedMessage = state["message"]
    parsed_intent = state["parsed_intent"]

    logger.info("orchestrator.node_check_availability", session_id=message.session_id)

    availability = await check_availability(parsed_intent, message.session_id)
    state["availability"] = availability

    if not availability.has_availability:
        state["response_text"] = (
            f"I'm sorry, there are no available slots for "
            f"{availability.service_type} service on {availability.query_date}. "
            f"Would you like me to check a different date?"
        )

    return state


async def node_resolve_conflict(state: dict) -> dict:
    """Node 3: Offer alternative slots."""
    message: NormalizedMessage = state["message"]
    availability = state["availability"]
    rejected_ids = state.get("rejected_slot_ids", [])

    logger.info("orchestrator.node_resolve_conflict", session_id=message.session_id)

    alternatives, response_text = resolve_conflict(
        availability, message.session_id, rejected_ids
    )

    state["alternative_slots"] = [s.model_dump() for s in alternatives]
    state["response_text"] = response_text

    return state


async def node_confirm_booking(state: dict) -> dict:
    """Node 4: Confirm and write booking."""
    message: NormalizedMessage = state["message"]
    availability = state["availability"]

    logger.info("orchestrator.node_confirm_booking", session_id=message.session_id)

    # Use selected slot or best available
    selected_slot = None
    if state.get("selected_slot"):
        from core.models import TimeSlot
        selected_slot = TimeSlot(**state["selected_slot"])
    elif availability and availability.slots:
        selected_slot = availability.slots[0]

    if not selected_slot:
        state["response_text"] = "I was unable to find a suitable slot. Please try again."
        return state

    # Build booking request
    request = BookingRequest(
        session_id=message.session_id,
        customer_name=message.customer_name or "Valued Customer",
        customer_phone=message.customer_phone or "",
        customer_email=message.customer_email,
        service_type=state["parsed_intent"].entities.service_type or ServiceType.GENERAL,
        slot=selected_slot,
        notes=state["parsed_intent"].entities.notes,
    )

    booking, response_text = await confirm_booking(request, message.session_id)

    if booking:
        state["booking"] = booking.model_dump()

    state["response_text"] = response_text

    # Add to conversation history
    history = state.get("conversation_history", [])
    history.append({"role": "assistant", "content": response_text})
    state["conversation_history"] = history

    return state


async def node_lookup_bookings(state: dict) -> dict:
    """Node 5: Look up existing bookings for cancel/reschedule."""
    message: NormalizedMessage = state["message"]

    logger.info("orchestrator.node_lookup_bookings", session_id=message.session_id)

    if not message.customer_phone:
        state["response_text"] = "I need your phone number to look up your bookings. Could you please provide it?"
        state["existing_bookings"] = []
        return state

    bookings, response_text = await lookup_bookings(
        message.customer_phone, message.session_id
    )

    state["existing_bookings"] = [b.model_dump() for b in bookings]
    state["response_text"] = response_text

    return state


async def node_cancel_booking(state: dict) -> dict:
    """Node 6: Cancel a booking."""
    message: NormalizedMessage = state["message"]

    logger.info("orchestrator.node_cancel_booking", session_id=message.session_id)

    existing = state.get("existing_bookings", [])
    if not existing:
        state["response_text"] = "No active bookings found to cancel."
        return state

    from core.models import BookingRecord
    booking = BookingRecord(**existing[0])

    success, response_text = await cancel_booking(booking, message.session_id)
    state["response_text"] = response_text

    return state


async def node_general_response(state: dict) -> dict:
    """Node 7: Handle general inquiries."""
    message: NormalizedMessage = state["message"]

    logger.info("orchestrator.node_general_response", session_id=message.session_id)

    state["response_text"] = (
        "I can help you schedule, reschedule, or cancel a service appointment. "
        "What would you like to do today?"
    )
    return state


async def node_unknown_response(state: dict) -> dict:
    """Node 8: Handle unknown or unclassified intent."""
    state["response_text"] = (
        "I'm sorry, I didn't quite understand that. "
        "I can help you book, reschedule, or cancel a service appointment. "
        "Could you please rephrase your request?"
    )
    return state


# ── Routing Functions ─────────────────────────────────────────────────────────

def route_by_intent(state: dict) -> str:
    """Route after intent parsing -- fully deterministic, no LLM judgment."""
    intent = state["parsed_intent"].intent

    routes = {
        Intent.BOOK: "check_availability",
        Intent.RESCHEDULE: "lookup_bookings",
        Intent.CANCEL: "lookup_bookings",
        Intent.CHECK_STATUS: "lookup_bookings",
        Intent.GENERAL_INQUIRY: "general_response",
        Intent.UNKNOWN: "unknown_response",
    }

    route = routes.get(intent, "unknown_response")
    logger.info("orchestrator.route_by_intent", intent=intent.value, route=route)
    return route


def route_after_availability(state: dict) -> str:
    """Route after availability check."""
    availability = state.get("availability")

    if not availability or not availability.has_availability:
        return "resolve_conflict"

    return "confirm_booking"


# ── Graph Assembly ────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    graph = StateGraph(dict)

    # Register all nodes
    graph.add_node("parse_intent", node_parse_intent)
    graph.add_node("check_availability", node_check_availability)
    graph.add_node("resolve_conflict", node_resolve_conflict)
    graph.add_node("confirm_booking", node_confirm_booking)
    graph.add_node("lookup_bookings", node_lookup_bookings)
    graph.add_node("cancel_booking", node_cancel_booking)
    graph.add_node("general_response", node_general_response)
    graph.add_node("unknown_response", node_unknown_response)

    # Entry point
    graph.set_entry_point("parse_intent")

    # Conditional routing after intent parsing
    graph.add_conditional_edges(
        "parse_intent",
        route_by_intent,
        {
            "check_availability": "check_availability",
            "lookup_bookings": "lookup_bookings",
            "general_response": "general_response",
            "unknown_response": "unknown_response",
        },
    )

    # Conditional routing after availability check
    graph.add_conditional_edges(
        "check_availability",
        route_after_availability,
        {
            "confirm_booking": "confirm_booking",
            "resolve_conflict": "resolve_conflict",
        },
    )

    # Linear edges
    graph.add_edge("resolve_conflict", END)
    graph.add_edge("confirm_booking", END)
    graph.add_edge("lookup_bookings", "cancel_booking")
    graph.add_edge("cancel_booking", END)
    graph.add_edge("general_response", END)
    graph.add_edge("unknown_response", END)

    return graph.compile()


# ── Public Interface ──────────────────────────────────────────────────────────

_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


async def run_agent(message: NormalizedMessage) -> dict:
    """
    Main entry point. Pass a NormalizedMessage, get back the final state.
    response_text in the returned state is what gets sent to the customer.
    """
    graph = get_graph()

    initial_state = {
        "message": message,
        "parsed_intent": None,
        "availability": None,
        "selected_slot": None,
        "booking": None,
        "response_text": "",
        "error": None,
        "turn_count": 0,
        "conversation_history": [],
        "existing_bookings": [],
        "alternative_slots": [],
        "rejected_slot_ids": [],
    }

    logger.info(
        "orchestrator.run_start",
        session_id=message.session_id,
        channel=message.channel.value,
    )

    final_state = await graph.ainvoke(initial_state)

    logger.info(
        "orchestrator.run_complete",
        session_id=message.session_id,
        response_length=len(final_state.get("response_text", "")),
    )

    return final_state