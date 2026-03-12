import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from core.config import get_settings
from core.models import (
    ParsedIntent,
    AvailabilityResult,
    TimeSlot,
    Intent,
    ServiceType,
)
from core.logger import get_logger
from datetime import datetime, timedelta

logger = get_logger(__name__)
settings = get_settings()


# ── Retry Policy ──────────────────────────────────────────────────────────────
# Retries up to 3 times on network errors with exponential backoff:
# Wait 1s, then 2s, then 4s between attempts.

@retry(
    stop=stop_after_attempt(settings.crm_max_retries),
    wait=wait_exponential(multiplier=1, min=settings.crm_retry_wait_seconds, max=8),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
    reraise=True,
)
async def _fetch_availability(
    client: httpx.AsyncClient,
    date: str,
    service_type: str,
    duration_minutes: int,
) -> dict:
    """Make HTTP GET to CRM availability endpoint with retry logic."""
    url = f"{settings.crm_base_url}/availability"
    params = {
        "date": date,
        "service_type": service_type,
        "duration_minutes": duration_minutes,
    }

    logger.info(
        "availability_agent.crm_request",
        url=url,
        params=params,
    )

    response = await client.get(url, params=params, timeout=10.0)
    response.raise_for_status()
    return response.json()


# ── Main Agent Function ───────────────────────────────────────────────────────

async def check_availability(
    parsed_intent: ParsedIntent,
    session_id: str,
) -> AvailabilityResult:
    """
    Check CRM availability based on parsed intent entities.
    Falls back to sensible defaults when entities are missing.
    Returns ranked list of available slots.
    """
    entities = parsed_intent.entities

    # Resolve service type -- default to "general" if not extracted
    service_type = (
        entities.service_type.value
        if entities.service_type
        else ServiceType.GENERAL.value
    )

    # Resolve date -- default to tomorrow if not specified
    if entities.preferred_date:
        date = entities.preferred_date
    else:
        date = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")
        logger.info(
            "availability_agent.date_fallback",
            session_id=session_id,
            resolved_date=date,
        )

    # Resolve duration
    duration_minutes = entities.duration_minutes or settings.default_slot_duration_minutes

    logger.info(
        "availability_agent.start",
        session_id=session_id,
        service_type=service_type,
        date=date,
        duration_minutes=duration_minutes,
    )

    try:
        async with httpx.AsyncClient() as client:
            data = await _fetch_availability(client, date, service_type, duration_minutes)

        slots = [TimeSlot(**s) for s in data.get("slots", [])]

        # Rank slots: prefer time closest to customer's preferred time
        slots = _rank_slots(slots, entities.preferred_time)

        result = AvailabilityResult(
            slots=slots,
            has_availability=len(slots) > 0,
            query_date=date,
            service_type=service_type,
        )

        logger.info(
            "availability_agent.success",
            session_id=session_id,
            total_slots=len(slots),
            has_availability=result.has_availability,
        )

        return result

    except httpx.HTTPStatusError as e:
        logger.error(
            "availability_agent.http_error",
            session_id=session_id,
            status_code=e.response.status_code,
            error=str(e),
        )
        return _empty_result(date, service_type)

    except Exception as e:
        logger.error(
            "availability_agent.failed",
            session_id=session_id,
            error=str(e),
        )
        return _empty_result(date, service_type)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _rank_slots(slots: list[TimeSlot], preferred_time: str | None) -> list[TimeSlot]:
    """
    Rank available slots by proximity to customer's preferred time.
    If no preference, return slots sorted by start time.
    """
    if not preferred_time:
        return sorted(slots, key=lambda s: s.start_time)

    try:
        preferred_hour = int(preferred_time.split(":")[0])
    except (ValueError, IndexError):
        return sorted(slots, key=lambda s: s.start_time)

    def proximity(slot: TimeSlot) -> int:
        slot_hour = int(slot.start_time.split(":")[0])
        return abs(slot_hour - preferred_hour)

    return sorted(slots, key=proximity)


def _empty_result(date: str, service_type: str) -> AvailabilityResult:
    """Return an empty result on API failure -- never crash the pipeline."""
    return AvailabilityResult(
        slots=[],
        has_availability=False,
        query_date=date,
        service_type=service_type,
    )