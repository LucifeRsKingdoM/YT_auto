"""Supabase client, used only in cloud mode for the storage bucket."""
from config import config

_client = None


def get_supabase():
    global _client
    if _client is None:
        from supabase import create_client
        if not config.SUPABASE_URL or not config.SUPABASE_SERVICE_KEY:
            raise RuntimeError(
                "DB_MODE=cloud requires SUPABASE_URL and SUPABASE_SERVICE_KEY "
                "in your .env file."
            )
        _client = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
    return _client
