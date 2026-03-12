from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional
from datetime import datetime


# ── Enums ────────────────────────────────────────────────────────────────────

class Channel(str, Enum):
    VOICE = "voice"
    CHAT = "chat"
    SMS = "sms"
    WHATSAPP = "whatsapp"


class Intent(str, Enum):
    BOOK = "book"
    RESCHEDULE = "reschedule"
    CANCEL = "cancel"
    CHECK_STATUS = "check_status"
    GENERAL_INQUIRY = "general_inquiry"
    UNKNOWN = "unknown"


class BookingStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    RESCHEDULED = "rescheduled"


class ServiceType(str, Enum):
    HVAC = "hvac"
    PLUMBING = "plumbing"
    ELECTRICAL = "electrical"
    CLEANING = "cleaning"
    PEST_CONTROL = "pest_control"
    LANDSCAPING = "landscaping"
    GENERAL = "general"


# ── Core Message Object ───────────────────────────────────────────────────────

class NormalizedMessage(BaseModel):
    """Unified message object passed through the entire agent pipeline."""
    session_id: str
    channel: Channel
    raw_text: str
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None
    customer_name: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict = Field(default_factory=dict)


# ── Intent Extraction ─────────────────────────────────────────────────────────

class ExtractedEntities(BaseModel):
    """Entities extracted from customer message by the Intent Parser."""
    service_type: Optional[ServiceType] = None
    preferred_date: Optional[str] = None        # ISO date string: "2025-01-15"
    preferred_time: Optional[str] = None        # "14:00"
    location: Optional[str] = None
    duration_minutes: Optional[int] = None
    notes: Optional[str] = None


class ParsedIntent(BaseModel):
    intent: Intent
    confidence: float = Field(ge=0.0, le=1.0)
    entities: ExtractedEntities
    raw_response: str = ""


# ── Availability ──────────────────────────────────────────────────────────────

class TimeSlot(BaseModel):
    slot_id: str
    team_id: str
    team_name: str
    date: str           # "2025-01-15"
    start_time: str     # "14:00"
    end_time: str       # "15:00"
    available: bool = True


class AvailabilityResult(BaseModel):
    slots: list[TimeSlot]
    has_availability: bool
    query_date: str
    service_type: str


# ── Booking ───────────────────────────────────────────────────────────────────

class BookingRequest(BaseModel):
    session_id: str
    customer_name: str
    customer_phone: str
    customer_email: Optional[str] = None
    service_type: ServiceType
    slot: TimeSlot
    notes: Optional[str] = None


class BookingRecord(BaseModel):
    booking_id: str
    session_id: str
    customer_name: str
    customer_phone: str
    customer_email: Optional[str] = None
    service_type: str
    team_id: str
    team_name: str
    date: str
    start_time: str
    end_time: str
    status: BookingStatus = BookingStatus.CONFIRMED
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ── Agent State (LangGraph) ───────────────────────────────────────────────────

class AgentState(BaseModel):
    """Shared state object that flows through every node in the LangGraph."""
    message: Optional[NormalizedMessage] = None
    parsed_intent: Optional[ParsedIntent] = None
    availability: Optional[AvailabilityResult] = None
    selected_slot: Optional[TimeSlot] = None
    booking: Optional[BookingRecord] = None
    response_text: str = ""
    error: Optional[str] = None
    turn_count: int = 0
    conversation_history: list[dict] = Field(default_factory=list)