import datetime as dt

from flask import Blueprint, render_template, jsonify, request

from database import get_session
from models import Video, Schedule, ActivityLog, YouTubeAccount
from security import login_required, current_user
from integrations import telegram

bp = Blueprint("schedule", __name__)


def parse_iso_to_utc(value):
    """Accept an ISO string (with Z or offset) and return naive UTC datetime."""
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
    user = current_user()
    s = get_session()
    try:
        # Fetch user's channels so the schedule page can filter/display by slot
        user_channels = s.query(YouTubeAccount).filter_by(owner_username=user).all()
        return render_template("schedule.html", channels=user_channels)
    finally:
        s.close()


@bp.route("/api/schedule/day")
@login_required
def day_view():
    """Given ?date=YYYY-MM-DD&slot=X, list scheduled and available draft videos strictly for that user/slot."""
    date_str = request.args.get("date")
    slot_filter = request.args.get("slot")
    user = current_user()

    if not date_str:
        return jsonify({"error": "date required"}), 400

    day_start = dt.datetime.fromisoformat(date_str + "T00:00:00")
    day_end = day_start + dt.timedelta(days=1)
    
    s = get_session()
    try:
        # Base query for scheduled videos restricted to current user
        scheduled_q = (
            s.query(Video)
            .join(Schedule, Schedule.video_id == Video.id)
            .join(YouTubeAccount, Video.youtube_account_id == YouTubeAccount.id)
            .filter(
                Video.owner_username == user,
                Schedule.scheduled_time >= day_start,
                Schedule.scheduled_time < day_end
            )
        )

        # Base query for available drafts restricted to current user
        available_q = (
            s.query(Video)
            .join(YouTubeAccount, Video.youtube_account_id == YouTubeAccount.id)
            .filter(
                Video.owner_username == user,
                Video.status == "draft",
                Video.file_key != ""
            )
        )

        # Apply slot filtering if requested
        if slot_filter:
            scheduled_q = scheduled_q.filter(YouTubeAccount.slot_number == int(slot_filter))
            available_q = available_q.filter(YouTubeAccount.slot_number == int(slot_filter))

        scheduled = scheduled_q.order_by(Schedule.scheduled_time.asc()).all()
        available = available_q.order_by(Video.created_at.asc()).all()

        return jsonify({
            "date": date_str,
            "scheduled": [{
                "id": v.id, 
                "title": v.title,
                "scheduled_time": v.schedule.scheduled_time.isoformat() + "Z",
                "slot": v.schedule.slot, 
                "status": v.schedule.status,
                "channel_name": v.youtube_account.channel_name if v.youtube_account else "Unassigned",
                "slot_number": v.youtube_account.slot_number if v.youtube_account else None
            } for v in scheduled],
            "available": [{
                "id": v.id, 
                "title": v.title,
                "channel_name": v.youtube_account.channel_name if v.youtube_account else "Unassigned",
                "slot_number": v.youtube_account.slot_number if v.youtube_account else None
            } for v in available],
        })
    finally:
        s.close()


@bp.route("/api/schedule/individual", methods=["POST"])
@login_required
def schedule_individual():
    """Body: {video_id, scheduled_time (ISO UTC)}."""
    data = request.get_json(force=True)
    when = parse_iso_to_utc(data.get("scheduled_time"))
    user = current_user()

    if not data.get("video_id") or not when:
        return jsonify({"error": "video_id and scheduled_time required"}), 400

    s = get_session()
    try:
        # Ensure user can only schedule their own videos
        v = s.query(Video).filter_by(id=int(data["video_id"]), owner_username=user).first()
        if not v:
            return jsonify({"error": "Video not found"}), 404

        _set_schedule(s, v, when, slot="", mode="individual")
        s.add(ActivityLog(actor=user, action="Scheduled video",
                          detail=f"{v.title} @ {when} UTC"))
        s.commit()
        telegram.notify_scheduled(v, when.isoformat())
        return jsonify({"ok": True})
    except Exception as exc:  
        s.rollback()
        return jsonify({"error": str(exc)}), 400
    finally:
        s.close()


@bp.route("/api/schedule/slots", methods=["POST"])
@login_required
def schedule_slots():
    data = request.get_json(force=True)
    date_str = data.get("date")
    slots = data.get("slots") or []
    video_ids = data.get("video_ids") or []
    tz_off = int(data.get("tz_offset_minutes", 0))  
    user = current_user()

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
            when_utc = local_dt + dt.timedelta(minutes=tz_off)
            
            v = s.query(Video).filter_by(id=int(vid), owner_username=user).first()
            if not v:
                continue
            _set_schedule(s, v, when_utc, slot=slot, mode="slot")
            assigned += 1

        s.add(ActivityLog(actor=user, action="Slot schedule",
                          detail=f"{assigned} videos across slots {', '.join(slots)}"))
        s.commit()
        return jsonify({"ok": True, "assigned": assigned})
    except Exception as exc:  
        s.rollback()
        return jsonify({"error": str(exc)}), 400
    finally:
        s.close()


@bp.route("/api/schedule/<int:video_id>", methods=["DELETE"])
@login_required
def unschedule(video_id):
    user = current_user()
    s = get_session()
    try:
        v = s.query(Video).filter_by(id=video_id, owner_username=user).first()
        if not v:
            return jsonify({"error": "Not found"}), 404
        if v.schedule:
            s.delete(v.schedule)
        if v.status == "scheduled":
            v.status = "draft"
        v.scheduled_time = None
        s.add(ActivityLog(actor=user, action="Unscheduled",
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