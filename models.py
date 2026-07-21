"""Database models.

Compatible with both Supabase PostgreSQL and local MySQL.
"""
import datetime as dt

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    BigInteger,
    ForeignKey,
    Boolean,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from database import Base


def utcnow():
    return dt.datetime.utcnow()


class Admin(Base):
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    safeword_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=utcnow)


# 1. New table to hold exactly 5 explicit account slots per user
class YouTubeAccount(Base):
    __tablename__ = 'youtube_accounts'
    
    id = Column(Integer, primary_key=True)
    owner_username = Column(String(50), nullable=False) 
    slot_number = Column(Integer, nullable=False)       # Will store 1, 2, 3, 4, or 5
    channel_name = Column(String(255), nullable=False)  
    credentials = Column(Text, nullable=False)          

    # This enforces that a user can only have one of each slot (e.g., only one "Channel 1")
    __table_args__ = (
        UniqueConstraint('owner_username', 'slot_number', name='uix_owner_slot'),
    )


class Video(Base):
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True)

    # Basic metadata
    title = Column(String(255), nullable=False)
    description = Column(Text, default="")
    tags = Column(String(500), default="")
    category_id = Column(String(10), default="22")
    privacy = Column(String(20), default="private")

    # Storage
    file_key = Column(String(500), default="")
    thumbnail_key = Column(String(500), default="")
    file_size = Column(BigInteger, default=0)

    # Lifecycle
    status = Column(String(20), default="draft")
    youtube_video_id = Column(String(40), default="")
    scheduled_time = Column(DateTime, nullable=True)
    published_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    # Multi-Tenant Ownership (Who uploaded it, and to which channel)
    owner_username = Column(String(50), nullable=False, default="Lucifer")
    youtube_account_id = Column(Integer, ForeignKey('youtube_accounts.id'), nullable=True)
    
    # Relationships
    youtube_account = relationship("YouTubeAccount")

    schedule = relationship(
        "Schedule",
        back_populates="video",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    failures = relationship(
        "UploadFailure",
        back_populates="video",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    stats = relationship(
        "VideoStat",
        back_populates="video",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class Schedule(Base):
    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True)

    video_id = Column(
        Integer,
        ForeignKey("videos.id"),
        nullable=False,
    )

    scheduled_time = Column(DateTime, nullable=False)
    slot = Column(String(10), default="")
    mode = Column(String(20), default="individual")
    status = Column(String(20), default="pending")
    created_at = Column(DateTime, default=utcnow)

    video = relationship(
        "Video",
        back_populates="schedule",
        lazy="selectin",
    )


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=utcnow, index=True)
    actor = Column(String(80), default="system")
    action = Column(String(120), nullable=False)
    detail = Column(Text, default="")


class UploadFailure(Base):
    __tablename__ = "upload_failures"

    id = Column(Integer, primary_key=True)

    video_id = Column(
        Integer,
        ForeignKey("videos.id"),
        nullable=False,
    )

    error_message = Column(Text, default="")
    log = Column(Text, default="")
    timestamp = Column(DateTime, default=utcnow)

    video = relationship(
        "Video",
        back_populates="failures",
        lazy="selectin",
    )


class Integration(Base):
    __tablename__ = "integrations"

    id = Column(Integer, primary_key=True)
    name = Column(String(80), unique=True, nullable=False)
    value_enc = Column(Text, default="")
    is_secret = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class VideoStat(Base):
    __tablename__ = "video_stats"

    id = Column(Integer, primary_key=True)

    video_id = Column(
        Integer,
        ForeignKey("videos.id"),
        nullable=False,
    )

    views = Column(BigInteger, default=0)
    likes = Column(BigInteger, default=0)
    comments = Column(BigInteger, default=0)
    watch_time_minutes = Column(BigInteger, default=0)
    fetched_at = Column(DateTime, default=utcnow)

    video = relationship(
        "Video",
        back_populates="stats",
        lazy="selectin",
    )