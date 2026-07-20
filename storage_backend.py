"""File storage abstraction.

DB_MODE=cloud  -> files go to a Supabase Storage bucket
DB_MODE=local  -> files go to a folder on disk

The rest of the app calls save_file / open_stream / delete_file / usage_bytes
and never cares which backend is active.
"""
import os
import shutil

from config import config


class LocalStorage:
    def __init__(self):
        self.root = os.path.abspath(config.LOCAL_STORAGE_DIR)
        os.makedirs(self.root, exist_ok=True)

    def save_file(self, key, src_path):
        dest = os.path.join(self.root, key)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy(src_path, dest)
        return key

    def local_path(self, key):
        """Absolute path usable directly for upload (local mode only)."""
        return os.path.join(self.root, key)

    def delete_file(self, key):
        p = os.path.join(self.root, key)
        if os.path.exists(p):
            os.remove(p)

    def usage_bytes(self):
        total = 0
        for dirpath, _dirs, files in os.walk(self.root):
            for f in files:
                total += os.path.getsize(os.path.join(dirpath, f))
        return total


class SupabaseStorage:
    def __init__(self):
        from integrations.supabase_client import get_supabase
        self.client = get_supabase()
        self.bucket = config.SUPABASE_BUCKET
        # ensure bucket exists (ignore if it already does)
        try:
            self.client.storage.create_bucket(self.bucket)
        except Exception:
            pass

    def save_file(self, key, src_path):
        with open(src_path, "rb") as fh:
            self.client.storage.from_(self.bucket).upload(
                key, fh, {"upsert": "true"}
            )
        return key

    def download_to(self, key, dest_path):
        data = self.client.storage.from_(self.bucket).download(key)
        with open(dest_path, "wb") as fh:
            fh.write(data)
        return dest_path

    def delete_file(self, key):
        try:
            self.client.storage.from_(self.bucket).remove([key])
        except Exception:
            pass

    def usage_bytes(self):
        total = 0
        try:
            items = self.client.storage.from_(self.bucket).list()
            for it in items:
                meta = it.get("metadata") or {}
                total += int(meta.get("size", 0) or 0)
        except Exception:
            pass
        return total


_backend = None


def get_storage():
    """Return the active storage backend (cached)."""
    global _backend
    if _backend is None:
        _backend = SupabaseStorage() if config.DB_MODE == "cloud" else LocalStorage()
    return _backend


def resolve_upload_path(video):
    """Give the YouTube uploader a real local file path to read from.

    Local mode: the file already lives on disk.
    Cloud mode: download it to a temp file first, return that path.
    """
    backend = get_storage()
    if isinstance(backend, LocalStorage):
        return backend.local_path(video.file_key), False  # (path, is_temp)
    # cloud: download to temp
    import tempfile
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(video.file_key)[1])
    tmp.close()
    backend.download_to(video.file_key, tmp.name)
    return tmp.name, True
