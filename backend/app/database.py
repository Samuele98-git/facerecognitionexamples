"""SQLAlchemy engine + session factory. Works with SQLite (default) or PostgreSQL."""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from . import config

# Make sure the SQLite folder exists before the engine opens the file.
if config.DATABASE_URL.startswith("sqlite"):
    os.makedirs("./data", exist_ok=True)

# check_same_thread=False lets camera worker threads share the SQLite connection.
connect_args = {"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(config.DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
