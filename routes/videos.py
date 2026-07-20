import io
import os
import tempfile
import datetime as dt

from flask import (
    Blueprint, render_template, jsonify, request, send_file
)
from werkzeug.utils import secure_filename

from database import get_session
from models import Video, UploadFailure, ActivityLog
from security import login_required, current_user
from storage_backend import get_storage

bp = Blueprint("videos", __name__)


@bp.route("/videos")
@login_required
def page():
    return render_template("videos.html")


@bp.route("/api/videos")
@login_required
def list_videos():
    """Tabbed list. ?tab=scheduled|uploaded|failed|all"""
    tab = request.args.get("tab", "all")
    s = get_session()
    try:
        q = s.query(Video)
        if tab == "scheduled":
            q = q.filter(Video.status == "scheduled")
        elif tab == "uploaded":
            q = q.filter(Video.status == "uploaded")
        elif tab == "failed":
            q = q.filter(Video.status == "failed")
        rows = q.order_by(Video.updated_at.desc()).all()
        out = []
        for v in rows:
            row = _row(v)
            if tab == "failed":
                fail = (
                    s.query(UploadFailure)
                    .filter_by(video_id=v.id)
                    .order_by(UploadFailure.timestamp.desc())
                    .first()
                )
                row["failure"] = {
                    "error_message": fail.error_message,
                    "log": fail.log,
                    "timestamp": fail.timestamp.isoformat() + "Z",
                } if fail else None
            out.append(row)
        return jsonify(out)
    finally:
        s.close()


@bp.route("/api/videos", methods=["POST"])
@login_required
def create_video():
    """Create a video record, optionally with an uploaded file."""
    s = get_session()
    try:
        title = request.form.get("title", "").strip()
        if not title:
            return jsonify({"error": "Title is required."}), 400
        v = Video(
            title=title,
            description=request.form.get("description", ""),
            tags=request.form.get("tags", ""),
            privacy=request.form.get("privacy", "private"),
            category_id=request.form.get("category_id", "22"),
        )
        s.add(v)
        s.flush()  # get v.id

        file = request.files.get("file")
        if file and file.filename:
            _store_upload(v, file)

        s.add(ActivityLog(actor=current_user(), action="Video added", detail=title))
        s.commit()
        return jsonify(_row(v)), 201
    except Exception as exc:  # noqa: BLE001
        s.rollback()
        return jsonify({"error": str(exc)}), 400
    finally:
        s.close()


@bp.route("/api/videos/<int:vid>", methods=["PUT"])
@login_required
def update_video(vid):
    s = get_session()
    try:
        v = s.get(Video, vid)
        if not v:
            return jsonify({"error": "Not found"}), 404
        data = request.get_json(force=True)
        for field in ("title", "description", "tags", "privacy", "category_id"):
            if field in data:
                setattr(v, field, data[field])
        s.add(ActivityLog(actor=current_user(), action="Video edited", detail=v.title))
        s.commit()
        return jsonify(_row(v))
    except Exception as exc:  # noqa: BLE001
        s.rollback()
        return jsonify({"error": str(exc)}), 400
    finally:
        s.close()


@bp.route("/api/videos/<int:vid>", methods=["DELETE"])
@login_required
def delete_video(vid):
    s = get_session()
    try:
        v = s.get(Video, vid)
        if not v:
            return jsonify({"error": "Not found"}), 404
        if v.file_key:
            get_storage().delete_file(v.file_key)
        title = v.title
        s.delete(v)
        s.add(ActivityLog(actor=current_user(), action="Video deleted", detail=title))
        s.commit()
        return jsonify({"ok": True})
    finally:
        s.close()


@bp.route("/api/videos/<int:vid>/file", methods=["POST"])
@login_required
def upload_file(vid):
    """Attach / replace the video file for an existing record."""
    s = get_session()
    try:
        v = s.get(Video, vid)
        if not v:
            return jsonify({"error": "Not found"}), 404
        file = request.files.get("file")
        if not file or not file.filename:
            return jsonify({"error": "No file provided"}), 400
        _store_upload(v, file)
        s.add(ActivityLog(actor=current_user(), action="File attached", detail=v.title))
        s.commit()
        return jsonify(_row(v))
    finally:
        s.close()


# ---- Excel import / export ---------------------------------------------
@bp.route("/api/videos/export.xlsx")
@login_required
def export_xlsx():
    from openpyxl import Workbook
    s = get_session()
    try:
        wb = Workbook()
        ws = wb.active
        ws.title = "Videos"
        headers = ["id", "title", "description", "tags", "privacy",
                   "status", "youtube_video_id", "scheduled_time"]
        ws.append(headers)
        for v in s.query(Video).order_by(Video.id).all():
            ws.append([
                v.id, v.title, v.description, v.tags, v.privacy, v.status,
                v.youtube_video_id,
                v.scheduled_time.isoformat() if v.scheduled_time else "",
            ])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return send_file(
            buf, as_attachment=True, download_name="videos.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    finally:
        s.close()


@bp.route("/api/videos/import.xlsx", methods=["POST"])
@login_required
def import_xlsx():
    """Bulk-add / update videos from an .xlsx file.

    Expected columns (first row = header): title, description, tags, privacy.
    Rows with an existing matching id are updated; others are created.
    """
    from openpyxl import load_workbook
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "No file provided"}), 400
    wb = load_workbook(file, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return jsonify({"error": "Empty file"}), 400
    header = [str(h).strip().lower() if h else "" for h in rows[0]]
    idx = {name: header.index(name) for name in header if name}

    s = get_session()
    created = updated = 0
    try:
        for r in rows[1:]:
            def cell(name, default=""):
                i = idx.get(name)
                return (r[i] if i is not None and i < len(r) and r[i] is not None
                        else default)
            title = str(cell("title")).strip()
            if not title:
                continue
            v = Video(
                title=title,
                description=str(cell("description")),
                tags=str(cell("tags")),
                privacy=str(cell("privacy", "private")) or "private",
            )
            s.add(v)
            created += 1
        s.add(ActivityLog(actor=current_user(), action="Excel import",
                          detail=f"{created} videos added"))
        s.commit()
        return jsonify({"created": created, "updated": updated})
    except Exception as exc:  # noqa: BLE001
        s.rollback()
        return jsonify({"error": str(exc)}), 400
    finally:
        s.close()


# ---- helpers ------------------------------------------------------------
def _store_upload(v, file):
    filename = secure_filename(file.filename)
    key = f"{v.id}_{filename}"
    # write to a temp file first, then hand to the storage backend
    tmp = tempfile.NamedTemporaryFile(delete=False)
    file.save(tmp.name)
    tmp.close()
    try:
        size = os.path.getsize(tmp.name)
        get_storage().save_file(key, tmp.name)
        v.file_key = key
        v.file_size = size
    finally:
        os.remove(tmp.name)


def _row(v):
    return {
        "id": v.id,
        "title": v.title,
        "description": v.description,
        "tags": v.tags,
        "privacy": v.privacy,
        "category_id": v.category_id,
        "status": v.status,
        "youtube_video_id": v.youtube_video_id,
        "file_key": v.file_key,
        "file_size": v.file_size,
        "scheduled_time": v.scheduled_time.isoformat() + "Z" if v.scheduled_time else None,
        "created_at": v.created_at.isoformat() + "Z" if v.created_at else None,
    }
