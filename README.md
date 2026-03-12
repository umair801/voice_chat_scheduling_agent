# AgAI-7: Voice and Chat AI Scheduling Agent

**By Muhammad Umair | [Datawebify](https://datawebify.com)**

A production-grade AI scheduling agent that handles customer appointment booking through voice calls and chat messages. Powered by Google Gemini 2.5 Flash and orchestrated with LangGraph, this system integrates directly into any field service business to eliminate manual scheduling entirely.

---

## Business Outcomes

| Metric | Manual Process | With AgAI-7 | Change |
|--------|---------------|-------------|--------|
| Average time to book | 8-15 minutes | Under 2 minutes | 85% faster |
| After-hours availability | 0% | 100% | Full coverage |
| Booking completion rate | 60-70% | 80%+ | +15-20% |
| Staff time on scheduling | 3-5 hours/day | Near zero | 90% reduction |
| No-show rate | 15-25% | Under 10% | 50% reduction |

---

## Target Industries

- HVAC, plumbing, electrical, and general field service companies
- Cleaning, pest control, and landscaping businesses
- Healthcare clinics and home care providers
- Any service business where scheduling is done manually or through a legacy CRM

---

## System Architecture

The system uses a LangGraph-orchestrated multi-agent pipeline where each agent has a single responsibility. Routing between agents is fully deterministic -- the LLM handles language, the graph handles flow.

```
Inbound Call / Message
        |
   Input Normalizer
        |
  Intent Parser Agent  (Gemini 2.5 Flash)
        |
  ┌─────┴──────┐
  |            |
Book       Cancel / Reschedule
  |            |
Availability   Lookup Bookings
Agent          Agent
  |
Conflict
Resolver
  |
Booking
Confirmation
Agent
  |
Supabase + Notifications
(SendGrid + Twilio SMS)
```

### Agent Responsibilities

**Input Normalizer** -- Converts raw voice transcriptions and chat messages into a unified message object. All downstream agents are channel-agnostic.

**Intent Parser Agent** -- Uses Gemini 2.5 Flash to classify intent (book, reschedule, cancel, check status, general inquiry) and extract entities (service type, date, time, location).

**Availability Agent** -- Makes structured REST calls to the CRM API with exponential backoff retry logic (max 3 retries). Returns slots ranked by proximity and team workload.

**Conflict Resolution Agent** -- When no exact slots match, proposes the three nearest alternatives and maintains full conversation state across turns.

**Booking Confirmation Agent** -- Writes confirmed appointments to Supabase, triggers email via SendGrid, and sends SMS confirmation via Twilio.

**Cancellation and Reschedule Agent** -- Looks up bookings by phone or email, handles cancellations within configurable policy windows, and re-enters the booking flow for reschedules.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Agent Framework | LangGraph |
| AI Model | Gemini 2.5 Flash (google.genai SDK) |
| Voice Interface | Twilio Voice (STT + TTS) |
| Chat Interface | FastAPI webhook (WhatsApp, SMS, web widget) |
| Backend API | FastAPI + Uvicorn |
| Database | Supabase (PostgreSQL) |
| Notifications | SendGrid (email) + Twilio (SMS) |
| Deployment | Docker + Railway |
| Language | Python 3.12 |

---

## API Endpoints

### Voice
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/voice/webhook` | Twilio voice webhook, STT input, TwiML response |
| POST | `/voice/status` | Twilio call status callback |
| GET | `/voice/test` | Health check for voice router |

### Chat
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/chat/webhook/twilio` | WhatsApp and SMS via Twilio |
| POST | `/chat/webhook/web` | Web widget and direct API |
| POST | `/chat/session/close` | Explicitly close a session |
| GET | `/chat/test` | Health check for chat router |

### Metrics
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/metrics?period=monthly` | Full business KPI dashboard |
| GET | `/metrics/health` | Health check for metrics router |

### Mock CRM
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/crm/availability` | Query team availability by date and service type |
| GET | `/crm/teams` | List all service teams |
| POST | `/crm/bookings` | Create a booking record |
| GET | `/crm/bookings/{customer_id}` | Fetch bookings by customer |

### System
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Project info |
| GET | `/health` | System health check |
| GET | `/docs` | Swagger UI (full API documentation) |

---

## Project Structure

```
AgAI_7_Voice_Chat_Scheduling_Agent/
├── agents/
│   ├── intent_parser.py         # Gemini-powered intent classification
│   ├── availability_agent.py    # CRM availability with retry logic
│   ├── conflict_resolver.py     # Alternative slot proposals
│   ├── booking_agent.py         # Booking confirmation and notifications
│   └── cancellation_agent.py    # Cancel and reschedule handling
├── core/
│   ├── orchestrator.py          # LangGraph conditional state graph
│   ├── config.py                # Pydantic settings and environment config
│   ├── database.py              # Supabase client and query functions
│   ├── session_manager.py       # Cross-turn conversation state persistence
│   ├── normalizer.py            # Voice and chat input normalization
│   ├── models.py                # All Pydantic data models
│   └── logger.py                # Structured JSON logging
├── api/
│   ├── main.py                  # FastAPI app assembly and middleware
│   ├── voice_router.py          # Twilio voice webhooks and TwiML
│   ├── chat_router.py           # Chat and SMS webhooks
│   ├── crm_mock.py              # Self-contained mock CRM API
│   └── metrics_router.py        # Business KPI dashboard endpoint
├── notifications/
│   ├── email_sender.py          # SendGrid email notifications
│   └── sms_sender.py            # Twilio SMS notifications
├── tests/
│   ├── test_intent_parser.py    # Intent and message model tests
│   ├── test_availability.py     # Availability and entity model tests
│   └── test_booking_flow.py     # Normalizer and booking flow tests
├── Dockerfile
├── railway.json
├── requirements.txt
├── .env.example
└── README.md
```

---

## Local Setup

### Prerequisites
- Python 3.12
- Docker Desktop
- A Supabase project
- A Google Gemini API key

### 1. Clone the repository

```bash
git clone https://github.com/umair801/voice_chat_scheduling_agent.git
cd agai7-scheduling-agent
```

### 2. Create virtual environment

```bash
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Mac/Linux
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` with your credentials.

### 5. Run the server

```bash
uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```

### 6. Run tests

```bash
pytest tests/ -v
```

---

## Environment Variables

```env
# Google Gemini
GEMINI_API_KEY=your_gemini_api_key

# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_anon_key

# Twilio
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=+1xxxxxxxxxx

# SendGrid
SENDGRID_API_KEY=SG.xxxxxxxxxxxxxxxxxxxxxxxxx
FROM_EMAIL=noreply@yourdomain.com

# App
APP_ENV=development
APP_HOST=0.0.0.0
APP_PORT=8000
```

---

## Docker Deployment

### Build

```bash
docker build -t agai7-scheduling-agent .
```

### Run

```bash
docker run --env-file .env -p 8000:8000 agai7-scheduling-agent
```

---

## Railway Deployment

1. Push this repository to GitHub
2. Create a new project at [railway.app](https://railway.app)
3. Connect your GitHub repository
4. Add all environment variables in the Railway dashboard
5. Railway auto-deploys on every push to main

Live deployment target: `https://scheduling.datawebify.com`

---

## Supabase Schema

Four tables power the persistence layer:

**bookings** -- All confirmed, cancelled, and rescheduled appointments with full customer and team details.

**sessions** -- Conversation state keyed by Twilio CallSid (voice) or phone number (chat). Enables multi-turn booking flows.

**teams** -- Service team registry with availability windows, service types, and coverage areas.

**agent_logs** -- Full audit trail of every agent event for debugging and analytics.

---

## Voice Flow

```
Customer calls Twilio number
        |
Twilio STT transcribes speech
        |
POST to /voice/webhook
        |
Agent pipeline runs
        |
TwiML response with Polly.Joanna TTS
        |
Customer hears the reply
        |
Loop continues until booking confirmed
```

## Chat Flow

```
Customer sends WhatsApp / SMS / web message
        |
POST to /chat/webhook/twilio or /chat/webhook/web
        |
Same agent pipeline as voice
        |
JSON or TwiML response returned
        |
Reply delivered to customer
```

---

## Metrics Dashboard

The `/metrics` endpoint returns real-time business KPIs pulled from Supabase:

- Booking volume (total, confirmed, cancelled, rescheduled)
- Booking completion rate
- Cancellation and reschedule rates
- After-hours booking percentage
- Average conversation turns to complete a booking
- Voice vs chat channel split
- Team utilization rates by service type
- Service type breakdown

---

## Portfolio

This is Project 7 of 50 in the Datawebify Agentic AI portfolio.

| Project | Description | URL |
|---------|-------------|-----|
| AgAI-1 | Enterprise WhatsApp Automation | whatsapp.datawebify.com |
| AgAI-2 | B2B Lead Generation System | leads.datawebify.com |
| AgAI-3 | Enterprise AI Support Agent | support.datawebify.com |
| AgAI-4 | RAG Knowledge Base Agent | rag.datawebify.com |
| AgAI-5 | Real Estate AI Domination System | reds.datawebify.com |
| AgAI-6 | Autonomous Research Agent | ara.datawebify.com |
| AgAI-7 | Voice and Chat Scheduling Agent | scheduling.datawebify.com |

---

## Contact

**Muhammad Umair**
Agentic AI Specialist and Enterprise Consultant
[datawebify.com](https://datawebify.com) | [github.com/umair801](https://github.com/umair801)
