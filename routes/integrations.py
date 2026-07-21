from flask import Blueprint, render_template, jsonify, request, redirect, flash, session

from database import get_session
from models import Admin, ActivityLog, YouTubeAccount
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
    from database import get_session
    from models import YouTubeAccount
    
    db = get_session()
    try:
        # Fetch only the channels belonging to the currently logged-in user
        user_channels = db.query(YouTubeAccount).filter_by(owner_username=current_user()).all()
        
        # Build a dictionary to represent exactly 5 slots
        channel_slots = {1: None, 2: None, 3: None, 4: None, 5: None}
        for ch in user_channels:
            channel_slots[ch.slot_number] = ch
            
        return render_template("integrations.html", channel_slots=channel_slots)
    finally:
        db.close()


@bp.route("/api/integrations")
@login_required
def get_integrations():
    """Return current values. Secrets are masked."""
    from database import get_session
    from models import YouTubeAccount
    
    user = current_user()
    db = get_session()
    try:
        user_has_channels = db.query(YouTubeAccount).filter_by(owner_username=user).count() > 0
    finally:
        db.close()

    out = {}
    for key, meta in EDITABLE.items():
        # Skip exposing YouTube client ID and secret to the frontend UI completely
        if key in ("yt_client_id", "yt_client_secret", "yt_default_privacy"):
            continue
        val = get_value(key, meta["default"]())
        out[key] = {
            "secret": meta["secret"],
            "value": _mask(val) if meta["secret"] else val,
            "is_set": bool(val),
        }
        
    return jsonify({
        "fields": out,
        "youtube_connected": user_has_channels,
        "scheduler": scheduler.status(),
        "db_mode": config.DB_MODE,
    })


@bp.route("/api/integrations", methods=["POST"])
@login_required
def save_integrations():
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
@bp.route("/integrations/youtube/authorize/<int:slot_number>")
@login_required
def yt_authorize(slot_number):
    if slot_number < 1 or slot_number > 5:
        flash("Invalid slot number.", "error")
        return redirect("/integrations")
        
    # Save the target slot number to the session so we know where to save the credentials when Google redirects back
    session['target_yt_slot'] = slot_number
    return redirect(youtube.build_auth_url())


@bp.route("/integrations/youtube/callback")
@login_required
def yt_callback():
    user = current_user()
    slot_number = session.get('target_yt_slot', 1) 
    
    # We pass the slot_number to youtube.py so it saves in the exact right database slot
    youtube.handle_callback(request.url, user, slot_number)
    
    s = get_session()
    try:
        s.add(ActivityLog(actor=user, action=f"YouTube Slot {slot_number} connected"))
        s.commit()
    finally:
        s.close()
        
    flash(f"YouTube channel successfully connected to Slot {slot_number}!", "success")
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