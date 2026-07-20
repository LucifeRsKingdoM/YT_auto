"""SQLAlchemy engine + session.

Works with both Supabase PostgreSQL and MySQL.
This version is configured to avoid DetachedInstanceError after commits.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, scoped_session, sessionmaker

from config import config

Base = declarative_base()

# Database Engine
engine = create_engine(
    config.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=1800,
    future=True,
)

# Session Factory
#
# expire_on_commit=False is VERY IMPORTANT.
# It prevents SQLAlchemy from expiring ORM objects after session.commit(),
# avoiding errors like:
#
# Parent instance <Video> is not bound to a Session;
# lazy load operation of attribute 'schedule' cannot proceed
#
SessionLocal = scoped_session(
    sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        future=True,
    )
)


def init_db():
    """Create all database tables if they do not already exist."""
    import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_session():
    """Return a new SQLAlchemy session."""
    return SessionLocal()


def close_session():
    """Dispose of the current scoped session."""
    SessionLocal.remove()