"""Telegram notifications via the Bot API (no extra SDK required)."""
import requests

from integrations.store import telegram_token, telegram_chat_id


def send_message(text: str) -> bool:
    token = telegram_token()
    chat_id = telegram_chat_id()
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=15,
        )
        return resp.ok
    except requests.RequestException:
        return False


def notify_upload_ok(video):
    send_message(
        f"✅ <b>Uploaded</b>\n{video.title}\n"
        f"https://youtu.be/{video.youtube_video_id}"
    )


def notify_upload_failed(video, error):
    send_message(
        f"❌ <b>Upload failed</b>\n{video.title}\n<code>{error}</code>"
    )


def notify_scheduled(video, when):
    send_message(
        f"🗓️ <b>Scheduled</b>\n{video.title}\nfor {when} (server time)"
    )
