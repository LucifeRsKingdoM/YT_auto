"""Password hashing (bcrypt), token encryption (Fernet), and auth helpers.

Nothing sensitive is ever stored in plaintext:
  - admin passwords and safe words -> bcrypt hashes
  - API tokens / keys              -> Fernet-encrypted strings
"""
import functools

import bcrypt
from cryptography.fernet import Fernet
from flask import session, redirect, url_for, request, jsonify

from config import config


# ---- password / safe-word hashing --------------------------------------
def hash_secret(raw: str) -> str:
    return bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def check_secret(raw: str, hashed: str) -> bool:
    if not raw or not hashed:
        return False
    try:
        return bcrypt.checkpw(raw.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


# ---- token encryption ---------------------------------------------------
def _fernet() -> Fernet:
    key = config.FERNET_KEY
    if not key:
        raise RuntimeError(
            "FERNET_KEY is not set. Generate one with:\n"
            '  python -c "from cryptography.fernet import Fernet;'
            'print(Fernet.generate_key().decode())"'
        )
    return Fernet(key.encode("utf-8"))


def encrypt(plaintext: str) -> str:
    if plaintext is None:
        plaintext = ""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")


# ---- login protection ---------------------------------------------------
def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user"):
            # For JSON/API calls return 401 so the frontend can react.
            if request.path.startswith("/api/"):
                return jsonify({"error": "auth_required"}), 401
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def current_user() -> str:
    return session.get("user", "")
