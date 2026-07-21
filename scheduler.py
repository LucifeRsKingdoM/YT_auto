"""Scheduler + upload runner.

Design choice for reliability: instead of trusting in-memory timers (which a
laptop loses when it sleeps), the source of truth is the `schedules` table.
A lightweight job ticks every 60 seconds and runs anything that is due, so a
job scheduled while the machine was asleep runs on the first tick after wake.

DUPLICATE-UPLOAD SAFETY (the important part):
  1. Each due schedule is CLAIMED atomically with a single
     UPDATE ... WHERE status='pending' statement. Only the caller whose
     UPDATE actually changed a row proceeds; everyone else exits. This makes
     it impossible for two ticks (or two processes) to upload the same video.
  2. `video.youtube_video_id` is a permanent idempotency key. Once it is set,
     the video is never uploaded again, even if its schedule somehow reappears.
  3. On ANY error the schedule is marked 'failed', NEVER put back to 'pending'.
     A failed schedule is not re-picked, so a single hiccup can no longer
     spiral into endless re-uploads that burn the daily YouTube quota.
"""
import datetime as dt
import os
import traceback

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import joinedload

from database import get_session
from models import Video, Schedule, UploadFailure, ActivityLog
from storage_backend import resolve_upload_path
from integrations import youtube, telegram

_scheduler = None
_paused = False


def log(session, action, detail="", actor="scheduler"):
    session.add(ActivityLog(action=action, detail=detail, actor=actor))


def run_upload(video_id: int):
    """Upload one video exactly once."""
    session = get_session()
    tmp_path = None
    is_temp = False

    try:
        # --- ATOMIC CLAIM -------------------------------------------------
        # Flip pending -> processing in one statement. `claimed` is the number
        # of rows changed. If it is 0, someone else already took this schedule
        # (or it is no longer pending) -> we do nothing and never upload twice.
        claimed = (
            session.query(Schedule)
            .filter(Schedule.video_id == video_id,
                    Schedule.status == "pending")
            .update({Schedule.status: "processing"},
                    synchronize_session=False)
        )
        session.commit()
        if not claimed:
            return

        video = (
            session.query(Video)
            .options(joinedload(Video.schedule))
            .filter(Video.id == video_id)
            .first()
        )
        if not video or not video.schedule:
            return

        # Idempotency guard: if this video already reached YouTube, mark the
        # (just-claimed) schedule done and stop. Never re-upload.
        if video.youtube_video_id or video.status == "uploaded":
            video.status = "uploaded"
            video.schedule.status = "done"
            session.commit()
            return

        video.status = "uploading"
        session.commit()

        # Resolve a real local file path for the uploader.
        tmp_path, is_temp = resolve_upload_path(video)

        # Upload to YouTube (raises on failure).
        yt_id = youtube.upload_video(video, tmp_path)

        # Record success. From here youtube_video_id is the permanent
        # idempotency key -- this video can never be uploaded again.
        video.youtube_video_id = yt_id
        video.status = "uploaded"
        video.published_at = dt.datetime.utcnow()
        video.schedule.status = "done"
        log(session, "Upload succeeded", f"{video.title} -> {yt_id}")
        session.commit()

        telegram.notify_upload_ok(
            title=video.title,
            youtube_id=yt_id,
            schedule_time=video.schedule.scheduled_time,
        )

    except Exception as exc:
        session.rollback()
        err = str(exc)
        tb = traceback.format_exc()

        video = (
            session.query(Video)
            .options(joinedload(Video.schedule))
            .filter(Video.id == video_id)
            .first()
        )
        if video:
            # Mark FAILED, not pending. A failed schedule is never auto-retried,
            # so errors can no longer cause repeated re-uploads. To try again,
            # re-schedule the video from the Schedule page (a deliberate action).
            video.status = "failed"
            if video.schedule:
                video.schedule.status = "failed"
            session.add(UploadFailure(video_id=video.id,
                                      error_message=err, log=tb))
            log(session, "Upload failed", f"{video.title}: {err}")
            session.commit()
            telegram.notify_upload_failed(title=video.title, error=err)

    finally:
        if is_temp and tmp_path:
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
    try:
        now = dt.datetime.utcnow()
        due = (
            session.query(Schedule)
            .filter(Schedule.status == "pending",
                    Schedule.scheduled_time <= now)
            .all()
        )
        due_ids = list({s.video_id for s in due})
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
