"""Configuration module for IDENT to AmoCRM integration."""

import os
from typing import Optional
from pydantic import BaseSettings, Field
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class DatabaseConfig(BaseSettings):
    """Database configuration."""
    host: str = Field(default="localhost", env="DB_HOST")
    port: int = Field(default=1433, env="DB_PORT")
    name: str = Field(default="PZ", env="DB_NAME")
    user: str = Field(default="sa", env="DB_USER")
    password: str = Field(env="DB_PASSWORD")
    driver: str = Field(default="{ODBC Driver 17 for SQL Server}", env="DB_DRIVER")
    
    @property
    def connection_string(self) -> str:
        """Get database connection string."""
        return (
            f"DRIVER={self.driver};"
            f"SERVER={self.host},{self.port};"
            f"DATABASE={self.name};"
            f"UID={self.user};"
            f"PWD={self.password}"
        )
    
    class Config:
        env_prefix = "DB_"


class AmoCRMConfig(BaseSettings):
    """AmoCRM configuration."""
    subdomain: str = Field(env="AMOCRM_SUBDOMAIN")
    client_id: str = Field(env="AMOCRM_CLIENT_ID")
    client_secret: str = Field(env="AMOCRM_CLIENT_SECRET")
    redirect_uri: str = Field(default="http://localhost:8080/callback", env="AMOCRM_REDIRECT_URI")
    access_token: Optional[str] = Field(default=None, env="AMOCRM_ACCESS_TOKEN")
    refresh_token: Optional[str] = Field(default=None, env="AMOCRM_REFRESH_TOKEN")
    
    @property
    def base_url(self) -> str:
        """Get AmoCRM API base URL."""
        return f"https://{self.subdomain}.amocrm.ru/api/v4"
    
    @property
    def oauth_url(self) -> str:
        """Get AmoCRM OAuth URL."""
        return f"https://{self.subdomain}.amocrm.ru/oauth2/access_token"
    
    class Config:
        env_prefix = "AMOCRM_"


class RedisConfig(BaseSettings):
    """Redis configuration for token storage."""
    host: str = Field(default="redis", env="REDIS_HOST")
    port: int = Field(default=6379, env="REDIS_PORT")
    db: int = Field(default=0, env="REDIS_DB")
    
    class Config:
        env_prefix = "REDIS_"


class SyncConfig(BaseSettings):
    """Synchronization configuration."""
    interval_minutes: int = Field(default=2, env="SYNC_INTERVAL_MINUTES")
    deep_sync_hour_morning: int = Field(default=8, env="DEEP_SYNC_HOUR_MORNING")
    deep_sync_hour_evening: int = Field(default=20, env="DEEP_SYNC_HOUR_EVENING")
    batch_size: int = Field(default=100, env="BATCH_SIZE")
    
    class Config:
        env_prefix = "SYNC_"


class AppConfig(BaseSettings):
    """Application configuration."""
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_file: str = Field(default="logs/sync.log", env="LOG_FILE")
    rate_limit_requests: int = Field(default=7, env="RATE_LIMIT_REQUESTS")
    rate_limit_period: int = Field(default=1, env="RATE_LIMIT_PERIOD")
    timezone: str = Field(default="Europe/Moscow", env="TIMEZONE")


# Initialize configurations
db_config = DatabaseConfig()
amocrm_config = AmoCRMConfig()
redis_config = RedisConfig()
sync_config = SyncConfig()
app_config = AppConfig()


# Field mapping configuration
FIELD_MAPPING = {
    "patient_id": 25,  # Primary key: IDENT patient ID
    "phone": 2,  # Secondary key: phone number
    "name": 1,  # Patient name
    "age": 3,  # Age
    "gender": 4,  # Gender
    "appointments": 5,  # Appointments
    "total_visits": 6,  # Total visit sum
    "card_number": 7,  # Card number
    "birthdate": 8,  # Date of birth
    "comment": 9,  # Comments
    "discount": 10,  # Discount
    "sms_opt_out": 11,  # SMS opt-out status
    "archive_reason": 12,  # Archive reason
    "status": 13,  # Patient status
    "snils": 14,  # SNILS
    "inn": 15,  # INN
    "branch": 16,  # Branch
    "patient_number": 17,  # Patient number
    "advance": 18,  # Advance payment
    "debt": 19,  # Debt
    # Add remaining fields as needed
} 