from pydantic_settings import BaseSettings
from typing import Optional
import os

class Settings(BaseSettings):
    app_name: str = "RAG Assistant"
    version: str = "1.0.0"
    debug: bool = False

    """Db"""
    database_url: str = "sqlite:///./rag_assitant.db"
    postgres_url: Optional[str] = None

    """Vector Store
    """
    vector_store_type: str = "chroma"
    vector_store_path: str = "./data/chroma"
    weaviate_url: Optional[str] = None

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_provider: str = "huggingface"
    openai_api_key: Optional[str] = None

    llm_provider: str = "gemini"
    gemini_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None

    """file process.
    """
    max_file_size: int =  50 * 1024 * 1024
    supported_formats: list = [".pdf", ".doc", ".docx", ".txt", ".md", ".xlsx", ".xls"]
    upload_path: str = "./uploads"

    chunk_size: int = 1000
    chunk_overlap: int = 200
    max_results: int = 10

    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()
