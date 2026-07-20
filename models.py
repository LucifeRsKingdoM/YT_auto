"""Database models. Identical schema on Supabase Postgres and local MySQL."""
import datetime as dt

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, BigInteger, ForeignKey, Boolean
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


class Video(Base):
    __tablename__ = "videos"
    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, default="")
    tags = Column(String(500), default="")          # comma separated
    category_id = Column(String(10), default="22")  # 22 = People & Blogs
    privacy = Column(String(20), default="private")  # private|unlisted|public
    # storage: key/path inside the active storage backend
    file_key = Column(String(500), default="")
    thumbnail_key = Column(String(500), default="")
    file_size = Column(BigInteger, default=0)        # bytes
    # lifecycle
    status = Column(String(20), default="draft")
    # draft | scheduled | uploading | uploaded | failed
    youtube_video_id = Column(String(40), default="")
    scheduled_time = Column(DateTime, nullable=True)
    published_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    schedule = relationship("Schedule", back_populates="video",
                            uselist=False, cascade="all, delete-orphan")
    failures = relationship("UploadFailure", back_populates="video",
                            cascade="all, delete-orphan")
    stats = relationship("VideoStat", back_populates="video",
                         uselist=False, cascade="all, delete-orphan")


class Schedule(Base):
    __tablename__ = "schedules"
    id = Column(Integer, primary_key=True)
    video_id = Column(Integer, ForeignKey("videos.id"), nullable=False)
    scheduled_time = Column(DateTime, nullable=False)
    slot = Column(String(10), default="")            # e.g. "08:00"
    mode = Column(String(20), default="individual")  # individual | slot
    status = Column(String(20), default="pending")   # pending | done | failed
    created_at = Column(DateTime, default=utcnow)

    video = relationship("Video", back_populates="schedule")


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
    video_id = Column(Integer, ForeignKey("videos.id"), nullable=False)
    error_message = Column(Text, default="")
    log = Column(Text, default="")
    timestamp = Column(DateTime, default=utcnow)

    video = relationship("Video", back_populates="failures")


class Integration(Base):
    """Single-row-ish key/value store for encrypted credentials & status."""
    __tablename__ = "integrations"
    id = Column(Integer, primary_key=True)
    name = Column(String(80), unique=True, nullable=False)  # e.g. youtube_token
    value_enc = Column(Text, default="")                    # Fernet-encrypted
    is_secret = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class VideoStat(Base):
    __tablename__ = "video_stats"
    id = Column(Integer, primary_key=True)
    video_id = Column(Integer, ForeignKey("videos.id"), nullable=False)
    views = Column(BigInteger, default=0)
    likes = Column(BigInteger, default=0)
    comments = Column(BigInteger, default=0)
    watch_time_minutes = Column(BigInteger, default=0)
    fetched_at = Column(DateTime, default=utcnow)

    video = relationship("Video", back_populates="stats")
