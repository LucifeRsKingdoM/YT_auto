"""Seed the two admin accounts from .env values on first run.

Passwords and safe words are stored only as bcrypt hashes. Re-running this is
safe: existing accounts are left untouched unless their password/safe word
in .env changed.
"""
from database import get_session, init_db
from models import Admin, ActivityLog
from security import hash_secret, check_secret
from config import config


def seed_admins():
    init_db()
    pairs = [
        (config.ADMIN1_USERNAME, config.ADMIN1_PASSWORD, config.ADMIN1_SAFEWORD),
        (config.ADMIN2_USERNAME, config.ADMIN2_PASSWORD, config.ADMIN2_SAFEWORD),
    ]
    s = get_session()
    try:
        for username, password, safeword in pairs:
            if not username or not password or not safeword:
                continue
            admin = s.query(Admin).filter_by(username=username).one_or_none()
            if admin is None:
                s.add(Admin(
                    username=username,
                    password_hash=hash_secret(password),
                    safeword_hash=hash_secret(safeword),
                ))
                s.add(ActivityLog(actor="system", action="Admin created",
                                  detail=username))
            else:
                # keep hashes in sync if .env values were rotated
                if not check_secret(password, admin.password_hash):
                    admin.password_hash = hash_secret(password)
                if not check_secret(safeword, admin.safeword_hash):
                    admin.safeword_hash = hash_secret(safeword)
        s.commit()
    finally:
        s.close()


if __name__ == "__main__":
    seed_admins()
    print("Admin accounts seeded.")
