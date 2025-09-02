#!/usr/bin/env python3
"""
Configuration settings for RAG System

ВРЕМЕННЫЕ ИЗМЕНЕНИЯ (для заказчиков):
- access_levels: все роли имеют доступ ко всем разделам для чтения
- detailed_access_levels: ограничения на загрузку/редактирование СОХРАНЕНЫ
- Это временное решение до готовности системы разделения по ролям
"""

from pydantic_settings import BaseSettings
from typing import Optional, List, Union
import os
from dotenv import load_dotenv
from pydantic import field_validator

# Load environment variables from .env file
load_dotenv()

class Settings(BaseSettings):
    # Основные настройки приложения
    app_name: str = "RAG Restaurant Management System"
    app_version: str = "1.0.0"
    debug: bool = True
    environment: str = "demo"
    
    # OpenAI API
    openai_api_key: str
    openai_model: str = "gpt-3.5-turbo"
    openai_max_tokens: int = 2000
    openai_temperature: float = 0.7
    
    # Embedding Settings
    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-small"
    embedding_openai_model: str = "text-embedding-3-small"
    
    # PostgreSQL Database
    database_url: str
    database_host: str = "localhost"
    database_port: int = 5432
    database_name: str = "rag_database"
    database_user: str = "username"
    database_password: str = "password"
    development_mode: bool = False
    local_database_url: Optional[str] = None
    
    # Supabase Configuration
    supabase_url: Optional[str] = None
    supabase_service_key: Optional[str] = None
    supabase_bucket: Optional[str] = None
    
    # Qdrant Vector Database (Cloud)
    qdrant_url: str
    qdrant_api_key: str
    qdrant_collection_name: str = "restaurant_documents"
    qdrant_vector_size: int = 1536
    
    # JWT Settings
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7
    
    # File Upload Settings
    upload_dir: str = "uploads"
    max_file_size: int = 10485760  # 10MB in bytes
    allowed_file_types: Union[str, List[str]] = ["pdf", "docx", "txt", "xlsx", "xls", "ppt", "pptx", "md", "csv", "rtf"]
    temp_dir: str = "temp"
    
    @field_validator('allowed_file_types', mode='before')
    @classmethod
    def parse_allowed_file_types(cls, v):
        if isinstance(v, str):
            return [x.strip() for x in v.split(',')]
        return v
    
    @field_validator('cors_origins', mode='before')
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [x.strip() for x in v.split(',')]
        return v
    
    # Server Settings
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 4
    reload: bool = True
    
    # Logging
    log_level: str = "INFO"
    log_file: str = "logs/app.log"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Security
    cors_origins: Union[str, List[str]] = ["http://localhost:3000", "http://localhost:8080"]
    secret_key: str
    
    # Rate Limiting
    rate_limit_per_minute: int = 60
    rate_limit_per_hour: int = 1000
    enable_rate_limiting: bool = True
    
    # Search Settings
    default_search_limit: int = 10
    default_score_threshold: float = 0.7
    max_context_size: int = 25
    
    # Session Management
    session_timeout_minutes: int = 60
    max_sessions_per_user: int = 10
    
    # External Services
    redis_url: Optional[str] = None
    celery_broker_url: Optional[str] = None
    
    # Environment Specific
    demo_mode: bool = True
    demo_user_email: str = "demo@restaurant.com"
    demo_user_password: str = "demo123"
    
    # Optional: Monitoring
    sentry_dsn: Optional[str] = None
    prometheus_enabled: bool = False
    
    # File Processing Configuration
    chunk_size: int = 500
    chunk_overlap: int = 50
    supported_formats: List[str] = [
        ".txt", ".pdf", ".doc", ".docx", 
        ".xls", ".xlsx", ".ppt", ".pptx", ".md", ".markdown",
        ".csv", ".rtf"
    ]
    
    # Access Control - используем реальные названия разделов
    # ВРЕМЕННО: все роли имеют доступ ко всем разделам для чтения
    access_levels: dict = {
        "restaurant_management": ["restaurant_ops", "procedures", "standards"],  # Временный полный доступ
        "kitchen_management": ["restaurant_ops", "procedures", "standards"],     # Временный полный доступ
        "concepts_recipes": ["restaurant_ops", "procedures", "standards"]        # Временный полный доступ
    }

    # Дополнительные уровни доступа для более детального контроля
    # ОСТАВЛЯЕМ для контроля загрузки документов
    detailed_access_levels: dict = {
        "restaurant_management": {
            "restaurant_ops": "full",  # Полный доступ к операциям ресторана
            "standards": "read_only",  # Только чтение стандартов
            "procedures": "read_only"  # Только чтение процедур
        },
        "kitchen_management": {
            "restaurant_ops": "none",  # Нет доступа к операциям ресторана
            "standards": "full",       # Полный доступ к стандартам
            "procedures": "full"       # Полный доступ к процедурам
        },
        "concepts_recipes": {
            "restaurant_ops": "none",  # Нет доступа к операциям ресторана
            "standards": "read_only",  # Только чтение стандартов
            "procedures": "full"       # Полный доступ к процедурам
        }
    }
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        env_prefix = ""

    @property
    def effective_database_url(self) -> str:
        """Get the effective database URL"""
        return self.database_url
    
    @property
    def qdrant_connection_params(self) -> dict:
        """Get Qdrant connection parameters for Cloud"""
        return {
            "url": self.qdrant_url,
            "api_key": self.qdrant_api_key,
            "collection_name": self.qdrant_collection_name,
            "vector_size": self.qdrant_vector_size
        }
    
    @property
    def is_production(self) -> bool:
        """Check if running in production mode"""
        return self.environment.lower() == "production"
    
    @property
    def is_demo(self) -> bool:
        """Check if running in demo mode"""
        return self.environment.lower() == "demo"

# Create global settings instance
settings = Settings()

# Validate required settings
def validate_settings():
    """Validate that all required settings are present"""
    required_fields = [
        "openai_api_key",
        "database_url", 
        "qdrant_url",
        "qdrant_api_key",
        "jwt_secret_key",
        "secret_key"
    ]
    
    missing_fields = []
    for field in required_fields:
        if not getattr(settings, field, None):
            missing_fields.append(field)
    
    if missing_fields:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_fields)}")
    
    return True

# Validate settings on import
try:
    validate_settings()
except ValueError as e:
    print(f"Configuration Error: {e}")
    print("Please check your .env file and ensure all required variables are set")
    raise
