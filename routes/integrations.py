from flask import Blueprint, render_template, jsonify, request, redirect

from database import get_session
from models import Admin, ActivityLog
from security import login_required, current_user, check_secret
from integrations import youtube
from integrations.store import get_value, set_value
from config import config
import scheduler

bp = Blueprint("integrations", __name__)

# Fields the UI can edit. Secrets are write-only (never sent back in full).
EDITABLE = {
    "yt_client_id": {"secret": False, "default": lambda: config.YT_CLIENT_ID},
    "yt_client_secret": {"secret": True, "default": lambda: config.YT_CLIENT_SECRET},
    "yt_default_privacy": {"secret": False, "default": lambda: config.YT_DEFAULT_PRIVACY},
    "telegram_bot_token": {"secret": True, "default": lambda: config.TELEGRAM_BOT_TOKEN},
    "telegram_chat_id": {"secret": False, "default": lambda: config.TELEGRAM_CHAT_ID},
    "supabase_url": {"secret": False, "default": lambda: config.SUPABASE_URL},
    "supabase_service_key": {"secret": True, "default": lambda: config.SUPABASE_SERVICE_KEY},
    "supabase_bucket": {"secret": False, "default": lambda: config.SUPABASE_BUCKET},
}


def verify_safeword(username, safeword):
    s = get_session()
    try:
        admin = s.query(Admin).filter_by(username=username).one_or_none()
        return bool(admin and check_secret(safeword, admin.safeword_hash))
    finally:
        s.close()


def _mask(value):
    if not value:
        return ""
    if len(value) <= 4:
        return "••••"
    return value[:2] + "••••" + value[-2:]


@bp.route("/integrations")
@login_required
def page():
    return render_template("integrations.html")


@bp.route("/api/integrations")
@login_required
def get_integrations():
    """Return current values. Secrets are masked."""
    out = {}
    for key, meta in EDITABLE.items():
        val = get_value(key, meta["default"]())
        out[key] = {
            "secret": meta["secret"],
            "value": _mask(val) if meta["secret"] else val,
            "is_set": bool(val),
        }
    return jsonify({
        "fields": out,
        "youtube_connected": youtube.is_connected(),
        "scheduler": scheduler.status(),
        "db_mode": config.DB_MODE,
    })


@bp.route("/api/integrations", methods=["POST"])
@login_required
def save_integrations():
    """Save credential changes. REQUIRES a valid safe word from the signed-in
    admin — this is the confirmation gate for any credential change."""
    data = request.get_json(force=True)
    safeword = data.get("safeword", "")
    changes = data.get("changes", {})

    if not verify_safeword(current_user(), safeword):
        return jsonify({"error": "Safe word is incorrect. No changes saved."}), 403
    if not changes:
        return jsonify({"error": "Nothing to change."}), 400

    applied = []
    for key, value in changes.items():
        if key not in EDITABLE:
            continue
        # Ignore untouched masked secret fields (frontend sends "" to skip)
        if EDITABLE[key]["secret"] and value == "":
            continue
        set_value(key, value)
        applied.append(key)

    s = get_session()
    try:
        s.add(ActivityLog(actor=current_user(), action="Credentials changed",
                          detail=", ".join(applied) or "none"))
        s.commit()
    finally:
        s.close()
    return jsonify({"ok": True, "applied": applied})


# ---- YouTube OAuth ------------------------------------------------------
@bp.route("/integrations/youtube/authorize")
@login_required
def yt_authorize():
    return redirect(youtube.build_auth_url())


@bp.route("/integrations/youtube/callback")
@login_required
def yt_callback():
    youtube.handle_callback(request.url)
    s = get_session()
    try:
        s.add(ActivityLog(actor=current_user(), action="YouTube connected"))
        s.commit()
    finally:
        s.close()
    return redirect("/integrations")


# ---- Scheduler control --------------------------------------------------
@bp.route("/api/scheduler/<action>", methods=["POST"])
@login_required
def scheduler_control(action):
    if action == "pause":
        scheduler.pause()
    elif action == "resume":
        scheduler.resume()
    else:
        return jsonify({"error": "unknown action"}), 400
    s = get_session()
    try:
        s.add(ActivityLog(actor=current_user(), action=f"Scheduler {action}d"))
        s.commit()
    finally:
        s.close()
    return jsonify(scheduler.status())
