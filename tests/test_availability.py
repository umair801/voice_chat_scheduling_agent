import pytest
from core.models import ExtractedEntities, ServiceType, Intent, ParsedIntent


def test_extracted_entities_defaults():
    entities = ExtractedEntities()
    assert entities.service_type is None
    assert entities.preferred_date is None
    assert entities.duration_minutes is None


def test_parsed_intent_structure():
    intent = ParsedIntent(
        intent=Intent.BOOK,
        confidence=0.95,
        entities=ExtractedEntities(service_type=ServiceType.HVAC),
        raw_response="Book HVAC",
    )
    assert intent.intent == Intent.BOOK
    assert intent.entities.service_type == ServiceType.HVAC
    assert intent.confidence == 0.95


def test_service_type_enum():
    assert ServiceType.HVAC == "hvac"
    assert ServiceType.PLUMBING == "plumbing"


def test_intent_enum():
    assert Intent.BOOK == "book"
    assert Intent.CANCEL == "cancel"
    assert Intent.RESCHEDULE == "reschedule"
