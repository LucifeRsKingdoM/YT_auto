"""SQLAlchemy engine + session. Works for both Supabase Postgres and MySQL
because we only ask config for the URL; the driver is chosen there.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session, declarative_base

from config import config

Base = declarative_base()

# For MySQL/Postgres a modest pool with pre-ping avoids stale connections
# on laptops that sleep or servers that idle.
engine = create_engine(
    config.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=1800,
    future=True,
)

SessionLocal = scoped_session(
    sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
)


def init_db():
    """Create all tables if they do not exist."""
    import models  # noqa: F401  (registers models on Base)
    Base.metadata.create_all(bind=engine)


def get_session():
    return SessionLocal()
