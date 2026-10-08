"""Environment-only secrets, redacted repr and strict startup validation."""
import os
from dataclasses import dataclass, field

from sqlalchemy.engine import URL


@dataclass(frozen=True)
class Settings:
    database_url: str | URL = field(repr=False)
    api_token: str = field(repr=False)
    database_timeout: float = 3.0
    evaluation_grace: float = 30.0
    patterns_mode: str = "off"
    pattern_timeout: float = 30.0
    live_sources: bool = False
    source_user_agent: str = 'PhotographyEventsCore-shadow (+https://github.com/Tmatz27/photography-events-core)'

    def __post_init__(self):
        if self.live_sources and self.patterns_mode!='shadow':
            raise ValueError('Live sources require explicit shadow mode')
        if (len(self.source_user_agent)<10 or not self.source_user_agent.isascii()
                or '\r' in self.source_user_agent or '\n' in self.source_user_agent):
            raise ValueError('A descriptive ASCII source User-Agent is required')
        if not 0.1 <= self.pattern_timeout <= 300:
            raise ValueError("CORE_PATTERN_TIMEOUT must be between 0.1 and 300 seconds")
        if self.patterns_mode not in ("off", "shadow"):
            raise ValueError("CORE_PATTERNS_MODE must be off or shadow; production promotion is not enabled")
        if len(self.api_token) < 32 or self.api_token.lower().startswith(('replace', 'changeme')):
            raise ValueError("CORE_API_TOKEN must be a generated secret of at least 32 characters")
        if not 0.1 <= self.database_timeout <= 30:
            raise ValueError("CORE_DATABASE_TIMEOUT must be between 0.1 and 30 seconds")
        if not 0 <= self.evaluation_grace <= 300:
            raise ValueError("CORE_EVALUATION_GRACE must be between 0 and 300 seconds")
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
        return cls(url, os.environ.get("CORE_API_TOKEN", ""), float(os.environ.get("CORE_DATABASE_TIMEOUT", "3")),
                   float(os.environ.get("CORE_EVALUATION_GRACE", "30")), os.environ.get("CORE_PATTERNS_MODE", "off"),
                   float(os.environ.get("CORE_PATTERN_TIMEOUT", "30")),
                   os.environ.get('CORE_LIVE_SOURCES','false').lower()=='true',
                   os.environ.get('CORE_SOURCE_USER_AGENT',cls.__dataclass_fields__['source_user_agent'].default))

