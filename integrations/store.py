"""Helpers to read/write integration credentials (encrypted) in the DB.

Values live in the `integrations` table, one row per key, Fernet-encrypted.
Defaults fall back to the .env config so the app works before anything is
edited in the UI.
"""
from database import get_session
from models import Integration
from security import encrypt, decrypt
from config import config


def set_value(name: str, value: str):
    s = get_session()
    try:
        row = s.query(Integration).filter_by(name=name).one_or_none()
        if row is None:
            row = Integration(name=name, value_enc=encrypt(value or ""))
            s.add(row)
        else:
            row.value_enc = encrypt(value or "")
        s.commit()
    finally:
        s.close()


def get_value(name: str, default: str = "") -> str:
    s = get_session()
    try:
        row = s.query(Integration).filter_by(name=name).one_or_none()
        if row and row.value_enc:
            return decrypt(row.value_enc)
        return default
    finally:
        s.close()


# Convenience getters that fall back to .env defaults ---------------------
def yt_client_id():
    return get_value("yt_client_id", config.YT_CLIENT_ID)


def yt_client_secret():
    return get_value("yt_client_secret", config.YT_CLIENT_SECRET)


def yt_default_privacy():
    return get_value("yt_default_privacy", config.YT_DEFAULT_PRIVACY)


def telegram_token():
    return get_value("telegram_bot_token", config.TELEGRAM_BOT_TOKEN)


def telegram_chat_id():
    return get_value("telegram_chat_id", config.TELEGRAM_CHAT_ID)
