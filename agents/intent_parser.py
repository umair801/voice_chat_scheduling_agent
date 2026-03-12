import json
import re
from datetime import datetime

from google import genai
from google.genai import types

from core.config import get_settings
from core.models import (
    NormalizedMessage,
    ParsedIntent,
    ExtractedEntities,
    Intent,
    ServiceType,
)
from core.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

_client = genai.Client(api_key=settings.gemini_api_key)

_SYSTEM_PROMPT = """You are an intent classification engine for a field service scheduling system.

Your job is to analyze a customer message and return a JSON object with exactly this structure:

{{
  "intent": "<one of: book, reschedule, cancel, check_status, general_inquiry, unknown>",
  "confidence": <float between 0.0 and 1.0>,
  "entities": {{
    "service_type": "<one of: hvac, plumbing, electrical, cleaning, pest_control, landscaping, general, or null>",
    "preferred_date": "<ISO date string YYYY-MM-DD or null>",
    "preferred_time": "<24-hour time HH:MM or null>",
    "location": "<address or area mentioned or null>",
    "duration_minutes": <integer or null>,
    "notes": "<any special instructions or null>"
  }}
}}

Rules:
- Return ONLY valid JSON. No markdown, no explanation, no preamble.
- Today's date is {today}. Resolve relative dates like "tomorrow", "next Tuesday", "this Friday" to actual ISO dates.
- If the customer mentions "AC", "air conditioning", or "furnace" -- service_type is "hvac".
- If no time is mentioned, preferred_time is null.
- If intent is cancel or check_status, entities can be mostly null.
- Confidence below 0.5 means intent is "unknown".
"""


async def parse_intent(message: NormalizedMessage) -> ParsedIntent:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    prompt = _SYSTEM_PROMPT.format(today=today)
    user_content = f"Customer message: {message.raw_text}"

    logger.info(
        "intent_parser.start",
        session_id=message.session_id,
        channel=message.channel.value,
        text=message.raw_text[:100],
    )

    try:
        response = _call_gemini(prompt, user_content)
        parsed = _parse_gemini_response(response)

        logger.info(
            "intent_parser.success",
            session_id=message.session_id,
            intent=parsed.intent.value,
            confidence=parsed.confidence,
            service_type=str(parsed.entities.service_type),
        )

        return parsed

    except Exception as e:
        logger.error(
            "intent_parser.failed",
            session_id=message.session_id,
            error=str(e),
        )
        return _fallback_intent(str(e))


def _call_gemini(system_prompt: str, user_content: str) -> str:
    full_prompt = f"{system_prompt}\n\n{user_content}"
    response = _client.models.generate_content(
        model=settings.gemini_model,
        contents=full_prompt,
        config=types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=512,
        ),
    )
    return response.text


def _parse_gemini_response(raw_response: str) -> ParsedIntent:
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw_response).strip()
    data = json.loads(cleaned)

    intent_str = data.get("intent", "unknown").lower()
    try:
        intent = Intent(intent_str)
    except ValueError:
        intent = Intent.UNKNOWN

    entities_data = data.get("entities", {})
    service_str = entities_data.get("service_type")
    try:
        service_type = ServiceType(service_str) if service_str else None
    except ValueError:
        service_type = ServiceType.GENERAL

    entities = ExtractedEntities(
        service_type=service_type,
        preferred_date=entities_data.get("preferred_date"),
        preferred_time=entities_data.get("preferred_time"),
        location=entities_data.get("location"),
        duration_minutes=entities_data.get("duration_minutes"),
        notes=entities_data.get("notes"),
    )

    return ParsedIntent(
        intent=intent,
        confidence=float(data.get("confidence", 0.5)),
        entities=entities,
        raw_response=raw_response,
    )


def _fallback_intent(error_msg: str) -> ParsedIntent:
    return ParsedIntent(
        intent=Intent.UNKNOWN,
        confidence=0.0,
        entities=ExtractedEntities(),
        raw_response=f"ERROR: {error_msg}",
    )