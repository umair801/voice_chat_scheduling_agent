from pydantic_settings import BaseSettings
from pydantic import Field
from enum import Enum
from functools import lru_cache


class AppEnv(str, Enum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"


class Settings(BaseSettings):
    # App
    app_env: AppEnv = AppEnv.DEVELOPMENT
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"
    gemini_model: str = "gemini-2.5-flash"

    # Google Gemini
    gemini_api_key: str = Field(..., env="GEMINI_API_KEY")

    # Supabase
    supabase_url: str = Field(..., env="SUPABASE_URL")
    supabase_key: str = Field(..., env="SUPABASE_KEY")

    # Twilio
    twilio_account_sid: str = Field(..., env="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str = Field(..., env="TWILIO_AUTH_TOKEN")
    twilio_phone_number: str = Field(..., env="TWILIO_PHONE_NUMBER")

    # SendGrid
    sendgrid_api_key: str = Field(..., env="SENDGRID_API_KEY")
    from_email: str = Field(..., env="FROM_EMAIL")

    # CRM Mock
    crm_base_url: str = "http://localhost:8000/crm"
    crm_max_retries: int = 3
    crm_retry_wait_seconds: float = 1.0

    # Booking policy
    cancellation_window_hours: int = 24
    max_alternative_slots: int = 3
    default_slot_duration_minutes: int = 60

    model_config = {"env_file": ".env", "case_sensitive": False}

# This line must exist -- it creates the singleton instance
settings = Settings()


@lru_cache()
def get_settings() -> Settings:
    return Settings()