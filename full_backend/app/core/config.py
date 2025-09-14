from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import validator, Field
import secrets


class Settings(BaseSettings):
    # API Configuration
    PROJECT_NAME: str = "Marches Publics API"
    PROJECT_VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"
    
    # Security
    SECRET_KEY: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Database
    MONGODB_URI: str = "mongodb://localhost:27017/"
    MONGODB_DB_NAME: str = "marches_publics"
    MONGODB_COLLECTION_NAME: str = "annonces"
    MONGODB_USER_COLLECTION: str = "users"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # CORS
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000"]
    ALLOWED_METHODS: List[str] = ["GET", "POST", "PUT", "DELETE"]
    ALLOWED_HEADERS: List[str] = ["*"]
    
    @validator("ALLOWED_ORIGINS", pre=True)
    def assemble_cors_origins(cls, v):
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)
    
    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 100
    RATE_LIMIT_PER_HOUR: int = 1000
    
    # Scraper Configuration
    BASE_URL: str = "https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseAdvancedSearch&searchAnnCons&keyWord="
    SCRAPER_DELAY_BETWEEN_REQUESTS: int = 2
    SCRAPER_REQUEST_TIMEOUT: int = 15
    SCRAPER_MAX_RETRIES: int = 3
    SCRAPER_USER_AGENT: str = "Mozilla/5.0 (API Scraper for Public Markets Analysis)"
    
    # PRADO Configuration
    PRADO_STATE_FIELD: str = "PRADO_PAGESTATE"
    PAGER_TARGET: str = "ctl0$CONTENU_PAGE$resultSearch$PagerTop$ctl2"
    NUM_PAGE_FIELD: str = "ctl0$CONTENU_PAGE$resultSearch$numPageTop"
    PRADO_POSTBACK_TARGET: str = "PRADO_POSTBACK_TARGET"
    
    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/api.log"
    LOG_ROTATION: str = "10 MB"
    LOG_RETENTION: str = "30 days"
    
    # Admin User
    ADMIN_EMAIL: str = "admin@marchespublics.ma"
    ADMIN_PASSWORD: str = "change-this-password"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
