import datetime as dt

from flask import Blueprint, render_template, jsonify, request

from database import get_session
from models import Video, ActivityLog, VideoStat
from security import login_required
from storage_backend import get_storage
import scheduler

bp = Blueprint("dashboard", __name__)


def _fmt_bytes(n):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


@bp.route("/")
@login_required
def page():
    return render_template("dashboard.html")


@bp.route("/api/dashboard/summary")
@login_required
def summary():
    s = get_session()
    try:
        total = s.query(Video).count()
        in_queue = s.query(Video).filter(
            Video.status.in_(["scheduled", "uploading"])
        ).count()
        published = s.query(Video).filter(Video.status == "uploaded").count()
        storage_bytes = get_storage().usage_bytes()
        return jsonify({
            "total": total,
            "in_queue": in_queue,
            "published": published,
            "storage_bytes": storage_bytes,
            "storage_human": _fmt_bytes(storage_bytes),
            "scheduler": scheduler.status(),
        })
    finally:
        s.close()


@bp.route("/api/dashboard/tile/<tile>")
@login_required
def tile(tile):
    """Return the video list behind a clicked dashboard tile."""
    s = get_session()
    try:
        q = s.query(Video)
        if tile == "in_queue":
            q = q.filter(Video.status.in_(["scheduled", "uploading"]))
        elif tile == "published":
            q = q.filter(Video.status == "uploaded")
        # "total" and "storage" -> all videos
        q = q.order_by(Video.updated_at.desc())
        return jsonify([_video_row(v) for v in q.all()])
    finally:
        s.close()


@bp.route("/api/dashboard/recent")
@login_required
def recent():
    s = get_session()
    try:
        vids = s.query(Video).order_by(Video.created_at.desc()).limit(15).all()
        return jsonify([_video_row(v) for v in vids])
    finally:
        s.close()


@bp.route("/api/dashboard/engagement")
@login_required
def engagement():
    """Near-real-time engagement overview + per-video list.

    Reads cached stats from the DB (refreshed by /refresh below) so the
    dashboard is instant; call refresh to pull fresh numbers from YouTube.
    """
    s = get_session()
    try:
        rows = (
            s.query(Video, VideoStat)
            .outerjoin(VideoStat, VideoStat.video_id == Video.id)
            .filter(Video.status == "uploaded")
            .all()
        )
        per_video = []
        totals = {"views": 0, "likes": 0, "comments": 0, "watch": 0}
        for v, st in rows:
            views = st.views if st else 0
            likes = st.likes if st else 0
            comments = st.comments if st else 0
            watch = st.watch_time_minutes if st else 0
            totals["views"] += views
            totals["likes"] += likes
            totals["comments"] += comments
            totals["watch"] += watch
            per_video.append({
                "id": v.id, "title": v.title,
                "youtube_video_id": v.youtube_video_id,
                "views": views, "likes": likes, "comments": comments,
                "watch_time_minutes": watch,
                "fetched_at": st.fetched_at.isoformat() + "Z" if st else None,
            })
        return jsonify({"totals": totals, "videos": per_video})
    finally:
        s.close()


@bp.route("/api/dashboard/engagement/refresh", methods=["POST"])
@login_required
def engagement_refresh():
    from integrations import youtube
    s = get_session()
    try:
        vids = s.query(Video).filter(
            Video.status == "uploaded", Video.youtube_video_id != ""
        ).all()
        id_map = {v.youtube_video_id: v for v in vids if v.youtube_video_id}
        stats = youtube.fetch_video_statistics(list(id_map.keys()))
        for yt_id, data in stats.items():
            v = id_map[yt_id]
            st = v.stats or VideoStat(video_id=v.id)
            st.views = data["views"]
            st.likes = data["likes"]
            st.comments = data["comments"]
            st.fetched_at = dt.datetime.utcnow()
            if v.stats is None:
                s.add(st)
        s.commit()
        return jsonify({"ok": True, "updated": len(stats)})
    except Exception as exc:  # noqa: BLE001
        s.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 400
    finally:
        s.close()


@bp.route("/api/dashboard/activity")
@login_required
def activity():
    """Last activity, paginated 10 at a time via ?page=N (0-based)."""
    page = max(0, int(request.args.get("page", 0)))
    per = 10
    s = get_session()
    try:
        total = s.query(ActivityLog).count()
        rows = (
            s.query(ActivityLog)
            .order_by(ActivityLog.timestamp.desc())
            .offset(page * per)
            .limit(per)
            .all()
        )
        return jsonify({
            "page": page,
            "has_prev": page > 0,
            "has_next": (page + 1) * per < total,
            "items": [{
                "timestamp": r.timestamp.isoformat() + "Z",
                "actor": r.actor,
                "action": r.action,
                "detail": r.detail,
            } for r in rows],
        })
    finally:
        s.close()


def _video_row(v):
    return {
        "id": v.id,
        "title": v.title,
        "status": v.status,
        "privacy": v.privacy,
        "youtube_video_id": v.youtube_video_id,
        "scheduled_time": v.scheduled_time.isoformat() + "Z" if v.scheduled_time else None,
        "file_size": v.file_size,
        "created_at": v.created_at.isoformat() + "Z" if v.created_at else None,
    }
