"""Configuration module using Pydantic Settings."""

from pathlib import Path
from typing import Literal

from pydantic import Field, BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

class ToleranceConfig(BaseModel):
     # Matching Thresholds
    amount_tolerance_percent: float = Field(
        default=10.0, description="Percentage tolerance for amount matching"
    )
    date_tolerance_days: int = Field(
        default=3, description="Number of days tolerance for date matching"
    )

class PromptConfig(BaseModel):
    # Display Settings
    show_reasoning: bool = Field(
        default=True, description="Show agent reasoning in responses"
    )
    response_tone: Literal["formal", "friendly"] = Field(
        default="formal", description="Tone of agent responses"
    )

class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

      # LLM Configuration
    llm_provider: Literal["gemini", "groq"] = Field(
        default="groq", description="LLM provider to use (gemini or groq)"
    )
    gemini_api_key: str = Field(default="", description="Google Gemini API key")
    gemini_model: str = Field(
        default="gemini-1.5-flash", description="Gemini model to use"
    )
    groq_api_key: str = Field(default="", description="Groq API key")
    groq_model: str = Field(
        default="openai/gpt-oss-120b", description="Groq model to use"
    )

    tolerance_config: ToleranceConfig = ToleranceConfig()

    prompt_config: PromptConfig = PromptConfig()

    default_currency: str = Field(default="USD", description="Default currency code")

    # Resilience Settings
    max_retries: int = Field(default=3, description="Maximum retry attempts for LLM calls")
    retry_backoff_base: float = Field(
        default=2.0, description="Base for exponential backoff"
    )
    rate_limit_rpm: int = Field(
        default=60, description="Rate limit in requests per minute"
    )
    circuit_breaker_threshold: int = Field(
        default=5, description="Failures before circuit breaker opens"
    )

    # Paths
    data_dir: Path = Field(default=Path("data"), description="Directory for data files")
    log_level: str = Field(default="INFO", description="Logging level")

    # Default user for demo
    default_user_id: str = Field(
        default="user_001", description="Default user ID for demo"
    )

    @property
    def transactions_file(self) -> Path:
        """Path to transactions JSON file."""
        return self.data_dir / "transactions.json"

    @property
    def merchants_file(self) -> Path:
        """Path to merchants JSON file."""
        return self.data_dir / "merchants.json"

    @property
    def sessions_dir(self) -> Path:
        """Path to sessions directory."""
        return self.data_dir / "sessions"

    @property
    def preferences_dir(self) -> Path:
        """Path to preferences directory."""
        return self.data_dir / "preferences"

    @property
    def disputes_dir(self) -> Path:
        """Path to disputes directory."""
        return self.data_dir / "disputes"


# Global settings instance
settings = Settings()
