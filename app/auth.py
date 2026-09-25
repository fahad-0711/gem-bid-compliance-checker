"""
Simple username/password auth for the Streamlit app.
Credentials are stored (hashed, never plaintext) in users.json next to this file.
"""

import json
import os
import hashlib
import hmac
import secrets

USERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "users.json")


def _load_users() -> dict:
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def _save_users(users: dict) -> None:
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), 100_000
    ).hex()


def register_user(username: str, password: str) -> tuple[bool, str]:
    """Returns (success, message)."""
    username = username.strip()
    if not username or not password:
        return False, "Username and password are required."

    users = _load_users()
    if username in users:
        return False, "That username is already taken."

    salt = secrets.token_hex(16)
    users[username] = {
        "salt": salt,
        "hash": _hash_password(password, salt),
    }
    _save_users(users)
    return True, "Registration successful. You can now log in."


def verify_user(username: str, password: str) -> bool:
    users = _load_users()
    record = users.get(username.strip())
    if not record:
        return False
    expected = _hash_password(password, record["salt"])
    return hmac.compare_digest(expected, record["hash"])
