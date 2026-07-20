import datetime as dt

from flask import Blueprint, render_template, jsonify, request

from database import get_session
from models import Video, Schedule, ActivityLog
from security import login_required, current_user
from integrations import telegram

bp = Blueprint("schedule", __name__)


def parse_iso_to_utc(value):
    """Accept an ISO string (with Z or offset) and return naive UTC datetime.

    The frontend sends local time already converted to UTC via toISOString(),
    so everything stored in the DB is UTC and matches the scheduler's clock.
    """
    if not value:
        return None
    v = value.replace("Z", "+00:00")
    d = dt.datetime.fromisoformat(v)
    if d.tzinfo is not None:
        d = d.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return d


@bp.route("/schedule")
@login_required
def page():
    return render_template("schedule.html")


@bp.route("/api/schedule/day")
@login_required
def day_view():
    """Given ?date=YYYY-MM-DD, list videos scheduled that day + those free
    to schedule (drafts with a file attached)."""
    date_str = request.args.get("date")
    if not date_str:
        return jsonify({"error": "date required"}), 400
    day_start = dt.datetime.fromisoformat(date_str + "T00:00:00")
    day_end = day_start + dt.timedelta(days=1)
    s = get_session()
    try:
        scheduled = (
            s.query(Video)
            .join(Schedule, Schedule.video_id == Video.id)
            .filter(Schedule.scheduled_time >= day_start,
                    Schedule.scheduled_time < day_end)
            .order_by(Schedule.scheduled_time.asc())
            .all()
        )
        available = (
            s.query(Video)
            .filter(Video.status == "draft", Video.file_key != "")
            .order_by(Video.created_at.asc())
            .all()
        )
        return jsonify({
            "date": date_str,
            "scheduled": [{
                "id": v.id, "title": v.title,
                "scheduled_time": v.schedule.scheduled_time.isoformat() + "Z",
                "slot": v.schedule.slot, "status": v.schedule.status,
            } for v in scheduled],
            "available": [{"id": v.id, "title": v.title} for v in available],
        })
    finally:
        s.close()


@bp.route("/api/schedule/individual", methods=["POST"])
@login_required
def schedule_individual():
    """Body: {video_id, scheduled_time (ISO UTC)}."""
    data = request.get_json(force=True)
    when = parse_iso_to_utc(data.get("scheduled_time"))
    if not data.get("video_id") or not when:
        return jsonify({"error": "video_id and scheduled_time required"}), 400
    s = get_session()
    try:
        v = s.get(Video, int(data["video_id"]))
        if not v:
            return jsonify({"error": "Video not found"}), 404
        _set_schedule(s, v, when, slot="", mode="individual")
        s.add(ActivityLog(actor=current_user(), action="Scheduled video",
                          detail=f"{v.title} @ {when} UTC"))
        s.commit()
        telegram.notify_scheduled(v, when.isoformat())
        return jsonify({"ok": True})
    except Exception as exc:  # noqa: BLE001
        s.rollback()
        return jsonify({"error": str(exc)}), 400
    finally:
        s.close()


@bp.route("/api/schedule/slots", methods=["POST"])
@login_required
def schedule_slots():
    """Body: {date:'YYYY-MM-DD', slots:['08:00','12:00','18:00'],
             video_ids:[...], tz_offset_minutes:int}

    Assigns video_ids in order into the slots. If there are more videos than
    slots, it rolls over to the next day(s). tz_offset_minutes is the browser's
    getTimezoneOffset() so 08:00 means 08:00 *local* to the user.
    """
    data = request.get_json(force=True)
    date_str = data.get("date")
    slots = data.get("slots") or []
    video_ids = data.get("video_ids") or []
    tz_off = int(data.get("tz_offset_minutes", 0))  # minutes to ADD to local->UTC
    if not date_str or not slots or not video_ids:
        return jsonify({"error": "date, slots and video_ids are required"}), 400

    s = get_session()
    assigned = 0
    try:
        base_day = dt.date.fromisoformat(date_str)
        for i, vid in enumerate(video_ids):
            day_offset = i // len(slots)
            slot = slots[i % len(slots)]
            hh, mm = [int(x) for x in slot.split(":")]
            local_dt = dt.datetime.combine(
                base_day + dt.timedelta(days=day_offset),
                dt.time(hour=hh, minute=mm),
            )
            # local -> UTC: getTimezoneOffset() is minutes to add to reach UTC
            when_utc = local_dt + dt.timedelta(minutes=tz_off)
            v = s.get(Video, int(vid))
            if not v:
                continue
            _set_schedule(s, v, when_utc, slot=slot, mode="slot")
            assigned += 1
        s.add(ActivityLog(actor=current_user(), action="Slot schedule",
                          detail=f"{assigned} videos across slots {', '.join(slots)}"))
        s.commit()
        return jsonify({"ok": True, "assigned": assigned})
    except Exception as exc:  # noqa: BLE001
        s.rollback()
        return jsonify({"error": str(exc)}), 400
    finally:
        s.close()


@bp.route("/api/schedule/<int:video_id>", methods=["DELETE"])
@login_required
def unschedule(video_id):
    s = get_session()
    try:
        v = s.get(Video, video_id)
        if not v:
            return jsonify({"error": "Not found"}), 404
        if v.schedule:
            s.delete(v.schedule)
        if v.status == "scheduled":
            v.status = "draft"
        v.scheduled_time = None
        s.add(ActivityLog(actor=current_user(), action="Unscheduled",
                          detail=v.title))
        s.commit()
        return jsonify({"ok": True})
    finally:
        s.close()


def _set_schedule(s, v, when_utc, slot, mode):
    if v.schedule:
        v.schedule.scheduled_time = when_utc
        v.schedule.slot = slot
        v.schedule.mode = mode
        v.schedule.status = "pending"
    else:
        s.add(Schedule(video_id=v.id, scheduled_time=when_utc,
                       slot=slot, mode=mode, status="pending"))
    v.scheduled_time = when_utc
    v.status = "scheduled"
