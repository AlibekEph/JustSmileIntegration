"""Configuration settings for IDENT to AmoCRM integration."""

import os
from typing import List, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


# Database configuration
class DatabaseConfig:
    def __init__(self):
        self.server = os.getenv('DB_SERVER', 'localhost')
        self.database = os.getenv('DB_DATABASE', 'IDENT')
        self.username = os.getenv('DB_USERNAME', 'sa')
        self.password = os.getenv('DB_PASSWORD', 'password')
        self.port = int(os.getenv('DB_PORT', '1433'))
        self.driver = os.getenv('DB_DRIVER', 'ODBC Driver 18 for SQL Server')
        
        # Connection timeout settings
        self.connection_timeout = int(os.getenv('DB_CONNECTION_TIMEOUT', '30'))
        self.command_timeout = int(os.getenv('DB_COMMAND_TIMEOUT', '30'))
        
        # SSL settings for ODBC
        self.trust_server_certificate = os.getenv('DB_TRUST_CERTIFICATE', 'yes')
        self.encrypt = os.getenv('DB_ENCRYPT', 'yes')
    
    @property
    def connection_string(self):
        """Generate connection string for pyodbc."""
        return (
            f"DRIVER={{{self.driver}}};"
            f"SERVER={self.server},{self.port};"
            f"DATABASE={self.database};"
            f"UID={self.username};"
            f"PWD={self.password};"
            f"TrustServerCertificate={self.trust_server_certificate};"
            f"Encrypt={self.encrypt};"
            f"Connection Timeout={self.connection_timeout};"
            f"Command Timeout={self.command_timeout};"
        )
    
    @property 
    def sqlalchemy_url(self):
        """Generate SQLAlchemy connection URL."""
        # URL encode the password to handle special characters
        from urllib.parse import quote_plus
        password_encoded = quote_plus(self.password)
        
        return (
            f"mssql+pyodbc://{self.username}:{password_encoded}@"
            f"{self.server}:{self.port}/{self.database}?"
            f"driver={quote_plus(self.driver)}&"
            f"TrustServerCertificate={self.trust_server_certificate}&"
            f"Encrypt={self.encrypt}"
        )


# AmoCRM configuration
class AmoCRMConfig:
    def __init__(self):
        self.subdomain = os.getenv('AMOCRM_SUBDOMAIN', '')
        self.client_id = os.getenv('AMOCRM_CLIENT_ID', '')
        self.client_secret = os.getenv('AMOCRM_CLIENT_SECRET', '')
        self.redirect_uri = os.getenv('AMOCRM_REDIRECT_URI', 'http://localhost:8080/callback')
        self.access_token = os.getenv('AMOCRM_ACCESS_TOKEN', '')
        self.refresh_token = os.getenv('AMOCRM_REFRESH_TOKEN', '')
        
        # API URLs
        self.base_url = f"https://{self.subdomain}.amocrm.ru/api/v4"
        self.oauth_url = f"https://{self.subdomain}.amocrm.ru/oauth2/access_token"


# Redis configuration
class RedisConfig:
    def __init__(self):
        self.host = os.getenv('REDIS_HOST', 'localhost')
        self.port = int(os.getenv('REDIS_PORT', '6379'))
        self.db = int(os.getenv('REDIS_DB', '0'))
        self.password = os.getenv('REDIS_PASSWORD', None)


# Sync configuration
class SyncConfig:
    def __init__(self):
        self.interval_minutes = int(os.getenv('SYNC_INTERVAL_MINUTES', '5'))
        self.batch_size = int(os.getenv('SYNC_BATCH_SIZE', '50'))
        self.deep_sync_hour_morning = int(os.getenv('DEEP_SYNC_HOUR_MORNING', '8'))
        self.deep_sync_hour_evening = int(os.getenv('DEEP_SYNC_HOUR_EVENING', '20'))


# Application configuration
class AppConfig:
    def __init__(self):
        self.log_level = os.getenv('LOG_LEVEL', 'INFO')
        self.log_file = os.getenv('LOG_FILE', 'logs/app.log')
        self.timezone = os.getenv('TIMEZONE', 'Europe/Moscow')
        self.rate_limit_requests = int(os.getenv('RATE_LIMIT_REQUESTS', '7'))
        self.rate_limit_period = int(os.getenv('RATE_LIMIT_PERIOD', '1'))


# AmoCRM pipeline and field configuration
AMOCRM_CONFIG = {
    "primary_pipeline_id": int(os.getenv('AMOCRM_PRIMARY_PIPELINE_ID', '0')),
    "secondary_pipeline_id": int(os.getenv('AMOCRM_SECONDARY_PIPELINE_ID', '0')),
    "default_stage_id": int(os.getenv('AMOCRM_DEFAULT_STAGE_ID', '0')),
    "excluded_stages": [int(x.strip()) for x in os.getenv('AMOCRM_EXCLUDED_STAGES', '').split(',') if x.strip()],
    "responsible_user_id": int(os.getenv('AMOCRM_RESPONSIBLE_USER_ID', '0')) if os.getenv('AMOCRM_RESPONSIBLE_USER_ID') else None
}

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
    "email": 20,  # Email address
    "completed_receptions_count": 21,  # Number of completed receptions
    "first_visit": 22,  # Date of first visit
    "last_visit": 23,  # Date of last visit
    "city": 24,  # City
    
    # Reception-specific fields
    "reception_id": 26,  # ID приёма
    "reception_date": 27,  # Дата приёма
    "doctor_name": 28,  # Врач
    "service_name": 29,  # Услуга
    "reception_cost": 30,  # Стоимость приёма
}

# Create configuration instances
db_config = DatabaseConfig()
amocrm_config = AmoCRMConfig()
redis_config = RedisConfig()
sync_config = SyncConfig()
app_config = AppConfig()