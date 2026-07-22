from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application configuration loaded from environment variables / .env file.
    Pydantic validates all fields on startup — any missing required var raises a clear error.
    
    Production features:
    - Multi-environment support (dev, staging, prod)
    - Configuration validation on startup
    - Rate limiting thresholds
    - Performance tuning knobs
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # MongoDB (separated credentials to avoid URI escaping issues)
    MONGO_USER: str = ""
    MONGO_PASSWORD: str = ""
    MONGO_HOST: str = ""  # e.g. cluster0.xxxxx.mongodb.net (no scheme)
    MONGO_DB: str = ""    # e.g. hrbot

    # Backward compatible fallback (may fail if username/password contain special characters)
    MONGODB_URI: str = "mongodb://localhost:27017/hrbot"
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""

    # Deployment
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = False

    # AI Provider
    AI_PROVIDER: Literal["google_genai", "groq"] = "google_genai"
    GEMINI_API_KEY: str = ""
    AI_MODEL_NAME: str = "gemini-2.0-flash"

    GROQ_API_KEY: str = ""
    GROQ_MODEL_NAME: str = "llama-3.1-8b-instant"
    GROQ_API_URL: str = "https://api.groq.com/openai/v1"

    # Company Info
    COMPANY_NAME: str = "TechNovance Solutions"
    HR_EMAIL: str = "hr@technovance.com"
    HR_PHONE: str = "+91-40-2345-6789"
    HRMS_PORTAL: str = "https://hrms.technovance.internal"
    
    # JWT Auth
    JWT_SECRET: str = "dev-secret-key-technovance-hr-ai-chatbot-2026"
    JWT_EXP_MINUTES: int = 1440
    ADMIN_JWT_EXP_MINUTES: int = 60  # Short-lived admin sessions (1 hour)

    # Super-Admin Credentials (never stored in DB — env-only)
    ADMIN_EMAIL: str = ""
    ADMIN_PASSWORD_HASH: str = ""  # bcrypt hash — run generate_hash.py to create

    # Admin-specific rate limit (much stricter than global)
    ADMIN_RATE_LIMIT_PER_MINUTE: int = 10

    # Vector Database (Pinecone)
    PINECONE_API_KEY: str = ""
    PINECONE_ENVIRONMENT: str = "us-east-1"
    PINECONE_INDEX_NAME: str = "hrbot-policies-employees"
    PINECONE_DIMENSION: int = 384  # Dimension for all-MiniLM-L6-v2 model
    
    # Embeddings Model
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"  # Lightweight & fast sentence-transformers model
    
    # Logging
    LOG_LEVEL: str = "INFO"

    # Security & CORS
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3005,http://127.0.0.1:3005"
    
    # Performance
    REQUEST_TIMEOUT_SECONDS: int = 30
    GROQ_MAX_RETRIES: int = 3
    GROQ_RETRY_BACKOFF_MS: int = 100
    CACHE_TTL_SECONDS: int = 3600
    
    # Rate Limiting (production safety)
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 60
    RATE_LIMIT_REQUESTS_PER_HOUR: int = 1000
    
    # Logging
    LOG_LEVEL: str = "INFO"

    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Normalize environment name."""
        return v.lower()

    @property
    def active_provider(self) -> str:
        return self.AI_PROVIDER.lower()

    @property
    def is_api_configured(self) -> bool:
        if self.active_provider == "groq":
            return bool(self.GROQ_API_KEY) and self.GROQ_API_KEY != "YOUR_GROQ_API_KEY"
        return bool(self.GEMINI_API_KEY) and self.GEMINI_API_KEY != "YOUR_GEMINI_API_KEY"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"


settings = Settings()
