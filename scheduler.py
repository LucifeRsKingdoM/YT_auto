"""Scheduler + upload runner.

Design choice for reliability: instead of trusting in-memory timers (which a
laptop loses when it sleeps), the source of truth is the `schedules` table.
A lightweight job ticks every 60 seconds and runs anything that is due.
That means a job scheduled for 08:00 while the machine was asleep runs on the
first tick after it wakes up — automatic catch-up, no lost uploads.
"""
import datetime as dt
import traceback

from apscheduler.schedulers.background import BackgroundScheduler

from database import get_session
from models import Video, Schedule, UploadFailure, ActivityLog
from storage_backend import resolve_upload_path
from integrations import youtube, telegram
from sqlalchemy.orm import joinedload
from models import Video

_scheduler = None
_paused = False


def log(session, action, detail="", actor="scheduler"):
    session.add(ActivityLog(action=action, detail=detail, actor=actor))


def run_upload(video_id: int):
    """Perform one upload. Records success/failure and notifies Telegram."""
    session = get_session()
    tmp_path = None
    is_temp = False
    try:
        # Use joinedload right here so the schedule relationship is fetched inside the session
        video = session.query(Video).options(joinedload(Video.schedule)).filter_by(id=video_id).first()
        if not video:
            return
        video.status = "uploading"
        session.commit()

        tmp_path, is_temp = resolve_upload_path(video)
        yt_id = youtube.upload_video(video, tmp_path)

        video.youtube_video_id = yt_id
        video.status = "uploaded"
        video.published_at = dt.datetime.utcnow()
        if video.schedule:
            video.schedule.status = "done"
        log(session, "Upload succeeded", f"{video.title} -> {yt_id}")
        session.commit()
        telegram.notify_upload_ok(video)
    except Exception as exc:  # noqa: BLE001 - we want to catch everything here
        session.rollback()
        video = session.query(Video).options(joinedload(Video.schedule)).filter_by(id=video_id).first()
        err = str(exc)
        tb = traceback.format_exc()
        if video:
            video.status = "failed"
            if video.schedule:
                video.schedule.status = "failed"
            session.add(UploadFailure(video_id=video.id, error_message=err, log=tb))
            log(session, "Upload failed", f"{video.title}: {err}")
            session.commit()
            telegram.notify_upload_failed(video, err)
    finally:
        if is_temp and tmp_path:
            import os
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        session.close()


def tick():
    """Run every due, pending schedule. Also serves as catch-up on startup."""
    if _paused:
        return
    session = get_session()
    due_ids = []
    try:
        now = dt.datetime.utcnow()
        due = (
            session.query(Schedule)
            .filter(Schedule.status == "pending", Schedule.scheduled_time <= now)
            .all()
        )
        due_ids = [s.video_id for s in due]
    finally:
        session.close()
    for vid in due_ids:
        run_upload(vid)


def start_scheduler():
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(tick, "interval", seconds=60, id="tick",
                       max_instances=1, coalesce=True)
    _scheduler.start()
    # immediate catch-up for anything missed while the app was off
    try:
        tick()
    except Exception:
        pass
    return _scheduler


def pause():
    global _paused
    _paused = True


def resume():
    global _paused
    _paused = False


def status():
    session = get_session()
    try:
        nxt = (
            session.query(Schedule)
            .filter(Schedule.status == "pending")
            .order_by(Schedule.scheduled_time.asc())
            .first()
        )
        return {
            "running": _scheduler is not None and not _paused,
            "paused": _paused,
            "next_run": nxt.scheduled_time.isoformat() + "Z" if nxt else None,
        }
    finally:
        session.close()