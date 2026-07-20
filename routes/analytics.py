import datetime as dt

from flask import Blueprint, render_template, jsonify, request

from security import login_required
from integrations import youtube

bp = Blueprint("analytics", __name__)


@bp.route("/analytics")
@login_required
def page():
    return render_template("analytics.html")


@bp.route("/api/analytics")
@login_required
def data():
    """Query params:
      preset = daily | weekly | monthly | yearly   (relative to today)
      OR
      start=YYYY-MM-DD & end=YYYY-MM-DD             (explicit range)
      OR
      days=2026-07-12,2026-07-13,2026-07-14         (specific days)
    """
    preset = request.args.get("preset")
    start = request.args.get("start")
    end = request.args.get("end")
    days = request.args.get("days")

    today = dt.date.today()

    try:
        if days:
            # specific, possibly non-contiguous days
            picked = sorted({dt.date.fromisoformat(d.strip())
                             for d in days.split(",") if d.strip()})
            if not picked:
                return jsonify({"error": "no valid days"}), 400
            # Analytics API needs a contiguous range; we fetch min..max then
            # filter to just the requested days.
            report = youtube.fetch_analytics(picked[0].isoformat(),
                                             picked[-1].isoformat())
            wanted = {d.isoformat() for d in picked}
            rows = [r for r in report.get("rows", []) if r[0] in wanted]
        else:
            if preset == "weekly":
                start_d, end_d = today - dt.timedelta(days=6), today
            elif preset == "monthly":
                start_d, end_d = today - dt.timedelta(days=29), today
            elif preset == "yearly":
                start_d, end_d = today - dt.timedelta(days=364), today
            elif preset == "daily":
                start_d, end_d = today, today
            elif start and end:
                start_d = dt.date.fromisoformat(start)
                end_d = dt.date.fromisoformat(end)
            else:
                start_d, end_d = today - dt.timedelta(days=29), today
            report = youtube.fetch_analytics(start_d.isoformat(), end_d.isoformat())
            rows = report.get("rows", [])

        # columns: day, views, estimatedMinutesWatched, likes, comments
        labels = [r[0] for r in rows]
        views = [r[1] for r in rows]
        watch = [r[2] for r in rows]
        likes = [r[3] for r in rows]
        comments = [r[4] for r in rows]
        return jsonify({
            "labels": labels,
            "series": {
                "views": views, "watch_minutes": watch,
                "likes": likes, "comments": comments,
            },
            "totals": {
                "views": sum(views), "watch_minutes": sum(watch),
                "likes": sum(likes), "comments": sum(comments),
            },
        })
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 400
