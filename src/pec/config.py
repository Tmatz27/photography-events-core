"""Environment-only secrets, redacted repr and strict startup validation."""
import os
from dataclasses import dataclass, field

from sqlalchemy.engine import URL


@dataclass(frozen=True)
class Settings:
    database_url: str | URL = field(repr=False)
    api_token: str = field(repr=False)
    database_timeout: float = 3.0

    def __post_init__(self):
        if len(self.api_token) < 32 or self.api_token.lower().startswith(('replace', 'changeme')):
            raise ValueError("CORE_API_TOKEN must be a generated secret of at least 32 characters")
        if not 0.1 <= self.database_timeout <= 30:
            raise ValueError("CORE_DATABASE_TIMEOUT must be between 0.1 and 30 seconds")
        if not str(self.database_url).startswith("postgresql+asyncpg://"):
            raise ValueError("Use a PostgreSQL asyncpg database URL")

    @classmethod
    def from_env(cls):
        url = os.environ.get("CORE_DATABASE_URL")
        if not url:
            password = os.environ.get("POSTGRES_PASSWORD", "")
            if not password:
                raise ValueError("POSTGRES_PASSWORD is required")
            url = URL.create("postgresql+asyncpg", username="photography_events", password=password,
                             host=os.environ.get("DB_HOST", "photography-events-db"),
                             database=os.environ.get("POSTGRES_DB", "photography_events"))
        return cls(url, os.environ.get("CORE_API_TOKEN", ""), float(os.environ.get("CORE_DATABASE_TIMEOUT", "3")))

