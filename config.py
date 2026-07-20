"""Central configuration. Reads the .env file and exposes settings.

The single most important switch here is DB_MODE:
  - "cloud" -> Supabase Postgres + Supabase Storage bucket
  - "local" -> local MySQL + local disk folder
The rest of the app never checks DB_MODE directly for the database URL;
it just asks this module for DATABASE_URL.
"""
import os
from dotenv import load_dotenv

load_dotenv()


def _get(key, default=None):
    val = os.getenv(key, default)
    return val


class Config:
    SECRET_KEY = _get("SECRET_KEY", "dev-insecure-change-me")
    FERNET_KEY = _get("FERNET_KEY", "")

    DB_MODE = (_get("DB_MODE", "local") or "local").strip().lower()

    # Supabase (cloud)
    SUPABASE_DB_URL = _get("SUPABASE_DB_URL", "")
    SUPABASE_URL = _get("SUPABASE_URL", "")
    SUPABASE_SERVICE_KEY = _get("SUPABASE_SERVICE_KEY", "")
    SUPABASE_BUCKET = _get("SUPABASE_BUCKET", "videos")

    # MySQL (local)
    MYSQL_HOST = _get("MYSQL_HOST", "127.0.0.1")
    MYSQL_PORT = _get("MYSQL_PORT", "3306")
    MYSQL_USER = _get("MYSQL_USER", "root")
    MYSQL_PASSWORD = _get("MYSQL_PASSWORD", "")
    MYSQL_DB = _get("MYSQL_DB", "yt_automation")
    LOCAL_STORAGE_DIR = _get("LOCAL_STORAGE_DIR", "storage/videos")

    # Admins
    ADMIN1_USERNAME = _get("ADMIN1_USERNAME", "Cipher")
    ADMIN1_PASSWORD = _get("ADMIN1_PASSWORD", "")
    ADMIN1_SAFEWORD = _get("ADMIN1_SAFEWORD", "")
    ADMIN2_USERNAME = _get("ADMIN2_USERNAME", "Lucifer")
    ADMIN2_PASSWORD = _get("ADMIN2_PASSWORD", "")
    ADMIN2_SAFEWORD = _get("ADMIN2_SAFEWORD", "")

    # YouTube
    YT_CLIENT_ID = _get("YT_CLIENT_ID", "")
    YT_CLIENT_SECRET = _get("YT_CLIENT_SECRET", "")
    YT_REDIRECT_URI = _get("YT_REDIRECT_URI", "http://localhost:5000/integrations/youtube/callback")
    YT_DEFAULT_PRIVACY = _get("YT_DEFAULT_PRIVACY", "private")

    # Telegram
    TELEGRAM_BOT_TOKEN = _get("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = _get("TELEGRAM_CHAT_ID", "")

    @property
    def DATABASE_URL(self):
        if self.DB_MODE == "cloud":
            if not self.SUPABASE_DB_URL:
                raise RuntimeError(
                    "DB_MODE=cloud but SUPABASE_DB_URL is empty. "
                    "Set it in your .env file."
                )
            return self.SUPABASE_DB_URL
        # local MySQL
        return (
            f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DB}?charset=utf8mb4"
        )


config = Config()
