from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.declarative import declarative_base
from config import settings
import logging

logger = logging.getLogger(__name__)

# Create database engine with fallback to local SQLite in development mode
try:
    engine = create_engine(
        settings.effective_database_url,
        pool_pre_ping=True,
        pool_recycle=300,
        echo=settings.debug
    )
    logger.info(f"Database engine created with URL: {settings.effective_database_url}")
except Exception as e:
    logger.warning(f"Failed to create database engine with {settings.effective_database_url}: {e}")
    if settings.development_mode:
        # Fallback to local SQLite
        logger.info("Falling back to local SQLite database")
        engine = create_engine(
            settings.local_database_url,
            pool_pre_ping=True,
            pool_recycle=300,
            echo=settings.debug
        )
    else:
        raise

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Import Base from models to ensure consistency
from .models import Base


def get_db() -> Session:
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Database session error: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def get_db_session() -> Session:
    """Get a single database session (not a generator)"""
    return SessionLocal()


def create_tables():
    """Create all database tables"""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Error creating database tables: {e}")
        raise


def drop_tables():
    """Drop all database tables"""
    try:
        Base.metadata.drop_all(bind=engine)
        logger.info("Database tables dropped successfully")
    except Exception as e:
        logger.error(f"Error dropping database tables: {e}")
        raise


def check_database_connection():
    """Check if database connection is working"""
    try:
        with engine.connect() as conn:
            # Use text() for SQLAlchemy 2.0+ compatibility
            from sqlalchemy import text
            conn.execute(text("SELECT 1"))
        logger.info("Database connection successful")
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False
