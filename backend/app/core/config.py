"""Application configuration settings for NEXUS."""

from typing import List, Optional
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration class loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Environment & Server
    NEXUS_ENV: str = "development"
    APP_NAME: str = "NEXUS"
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    # Security & Authentication
    SECRET_KEY: str = "nexus-hackathon-super-secret-key-32bytes-minimum"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173"

    @property
    def cors_origins_list(self) -> List[str]:
        """Convert comma-separated CORS origins into a string list."""
        if isinstance(self.CORS_ORIGINS, str):
            return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]
        return self.CORS_ORIGINS

    # Database
    DATABASE_URL: str = "sqlite:///./data/nexus.db"

    # Storage & File System
    NEXUS_STORAGE_DIR: str = "./data/nexus"
    MAX_UPLOAD_SIZE_BYTES: int = 20 * 1024 * 1024  # 20 MB
    ALLOWED_EXTENSIONS: str = "pdf,docx,txt"

    @property
    def allowed_extensions_list(self) -> List[str]:
        """Get allowed extensions list in lowercase."""
        return [ext.strip().lower() for ext in self.ALLOWED_EXTENSIONS.split(",") if ext.strip()]

    # Vector Store Consolidation (PostgreSQL + pgvector vs ChromaDB)
    VECTOR_STORE_BACKEND: str = "postgres_pgvector"  # 'postgres_pgvector' or 'chroma'
    PGVECTOR_INDEX_TYPE: str = "hnsw"
    PGVECTOR_M: int = 16
    PGVECTOR_EF_CONSTRUCTION: int = 64

    # Vector Store (ChromaDB - Legacy / Migration Transition)
    CHROMA_PERSIST_DIR: str = "./data/chroma"

    # Rate Limiting & Resource Protection
    RATE_LIMIT_PER_MINUTE: int = 120
    RATE_LIMIT_BURST: int = 40

    # Local Inference & Embedding Models
    EMBEDDING_MODEL_NAME: str = "all-MiniLM-L6-v2"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL_NAME: str = "llama3.2:3b"
    OLLAMA_TIMEOUT_SECONDS: int = 45
    INFERENCE_CONCURRENCY_LIMIT: int = 2
    INFERENCE_QUEUE_LIMIT: int = 16
    INFERENCE_WAIT_TIMEOUT_SECONDS: float = 30.0

    # Guardrails & Grounding Verification
    MIN_GROUNDING_SCORE: float = 0.65
    ENABLE_PERMISSION_GUARD: bool = True
    ENABLE_INTEGRITY_CHECK: bool = True
    ENABLE_QUALITY_INSPECTION: bool = True

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        """Verify strict cryptographic secret hygiene in production environments."""
        if self.NEXUS_ENV == "production":
            insecure_defaults = {
                "nexus-hackathon-super-secret-key-32bytes-minimum",
                "changeme",
                "secret",
                "default",
                "admin",
            }
            if self.SECRET_KEY in insecure_defaults or len(self.SECRET_KEY) < 32:
                raise ValueError(
                    "In production (NEXUS_ENV='production'), SECRET_KEY must be a cryptographically strong "
                    "secret of at least 32 characters and cannot match known defaults."
                )
        return self


settings = Settings()

