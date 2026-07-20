"""Telegram notifications via the Bot API."""

from __future__ import annotations

import datetime as dt

import requests

from integrations.store import telegram_chat_id, telegram_token


def send_message(text: str) -> bool:
    """Send a Telegram message.

    Returns True on success, False otherwise.
    """
    token = telegram_token()
    chat_id = telegram_chat_id()

    if not token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    try:
        response = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
            },
            timeout=15,
        )
        return response.ok

    except requests.RequestException:
        return False


def notify_upload_ok(
    title: str,
    youtube_id: str,
    schedule_time: dt.datetime | None = None,
) -> bool:
    """Notify successful upload."""

    message = (
        f"✅ <b>Upload Successful</b>\n\n"
        f"📹 <b>{title}</b>\n"
        f"🔗 https://youtu.be/{youtube_id}"
    )

    if schedule_time:
        message += (
            f"\n🕒 Scheduled: "
            f"{schedule_time.strftime('%Y-%m-%d %H:%M:%S')} UTC"
        )

    return send_message(message)


def notify_upload_failed(
    title: str,
    error: str,
) -> bool:
    """Notify failed upload."""

    message = (
        f"❌ <b>Upload Failed</b>\n\n"
        f"📹 <b>{title}</b>\n\n"
        f"<code>{error}</code>"
    )

    return send_message(message)


def notify_scheduled(
    title: str,
    when,
) -> bool:
    """Notify that a video has been scheduled."""

    message = (
        f"🗓️ <b>Video Scheduled</b>\n\n"
        f"📹 <b>{title}</b>\n"
        f"🕒 {when}"
    )

    return send_message(message)