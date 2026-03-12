from core.config import get_settings
from core.models import (
    AvailabilityResult,
    TimeSlot,
    ParsedIntent,
    AgentState,
)
from core.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


def resolve_conflict(
    availability: AvailabilityResult,
    session_id: str,
    rejected_slot_ids: list[str] | None = None,
) -> tuple[list[TimeSlot], str]:
    """
    Given availability results and any previously rejected slots,
    return up to 3 alternative slots and a natural language response.

    Returns:
        alternatives: list of up to 3 TimeSlot options
        response_text: natural language message to send to the customer
    """
    rejected_slot_ids = rejected_slot_ids or []

    # Filter out any slots the customer already rejected
    remaining = [
        slot for slot in availability.slots
        if slot.slot_id not in rejected_slot_ids
    ]

    logger.info(
        "conflict_resolver.start",
        session_id=session_id,
        total_slots=len(availability.slots),
        rejected_count=len(rejected_slot_ids),
        remaining=len(remaining),
    )

    if not remaining:
        logger.warning(
            "conflict_resolver.no_slots_remaining",
            session_id=session_id,
        )
        return [], _build_no_availability_response(availability)

    # Take top 3 remaining slots
    alternatives = remaining[:settings.max_alternative_slots]

    response_text = _build_alternatives_response(alternatives, availability.service_type)

    logger.info(
        "conflict_resolver.resolved",
        session_id=session_id,
        alternatives_count=len(alternatives),
    )

    return alternatives, response_text


def select_slot_from_alternatives(
    alternatives: list[TimeSlot],
    customer_choice: str,
) -> TimeSlot | None:
    """
    Match customer's spoken/typed choice to one of the offered alternatives.
    Handles choices like "first", "1", "option 1", "14:00", "2pm".
    Returns the matched slot or None if no match found.
    """
    choice = customer_choice.lower().strip()

    # Match by ordinal word
    ordinal_map = {
        "first": 0, "1st": 0, "one": 0, "1": 0, "option 1": 0,
        "second": 1, "2nd": 1, "two": 1, "2": 1, "option 2": 1,
        "third": 2, "3rd": 2, "three": 2, "3": 2, "option 3": 2,
    }

    if choice in ordinal_map:
        idx = ordinal_map[choice]
        if idx < len(alternatives):
            return alternatives[idx]

    # Match by time mention (e.g. "2pm", "14:00", "10am")
    for slot in alternatives:
        slot_hour = int(slot.start_time.split(":")[0])

        # Check 24h format
        if slot.start_time in choice:
            return slot

        # Check 12h format
        am_pm = "am" if slot_hour < 12 else "pm"
        display_hour = slot_hour if slot_hour <= 12 else slot_hour - 12
        if f"{display_hour}{am_pm}" in choice or f"{display_hour} {am_pm}" in choice:
            return slot

    # Match by team name
    for slot in alternatives:
        if slot.team_name.lower() in choice:
            return slot

    return None


def build_confirmation_prompt(slot: TimeSlot, service_type: str) -> str:
    """Build a confirmation message before finalizing a booking."""
    hour = int(slot.start_time.split(":")[0])
    am_pm = "AM" if hour < 12 else "PM"
    display_hour = hour if hour <= 12 else hour - 12

    return (
        f"I have {service_type.upper()} service available on {slot.date} "
        f"at {display_hour}:00 {am_pm} with {slot.team_name}. "
        f"Shall I confirm this booking? Please say yes or no."
    )


# ── Response Builders ─────────────────────────────────────────────────────────

def _build_alternatives_response(
    alternatives: list[TimeSlot],
    service_type: str,
) -> str:
    if not alternatives:
        return "I'm sorry, there are no available slots for that service at this time."

    lines = [f"Here are the available options for {service_type} service:"]

    for i, slot in enumerate(alternatives, 1):
        hour = int(slot.start_time.split(":")[0])
        am_pm = "AM" if hour < 12 else "PM"
        display_hour = hour if hour <= 12 else hour - 12
        lines.append(
            f"Option {i}: {slot.date} at {display_hour}:00 {am_pm} with {slot.team_name}"
        )

    lines.append("Which option works best for you?")
    return "\n".join(lines)


def _build_no_availability_response(availability: AvailabilityResult) -> str:
    return (
        f"I'm sorry, there are no available slots for {availability.service_type} "
        f"service on {availability.query_date}. "
        f"Would you like me to check availability for a different date?"
    )