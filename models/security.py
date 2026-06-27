# -*- coding: utf-8 -*-
"""Administrator-key storage and verification for restricted application modes."""
import getpass
import hashlib
import hmac
import json
import os
import tempfile
from typing import Optional


CONFIG_DIR = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")),
    "IPQ_LFR",
)
CONFIG_FILE = os.path.join(CONFIG_DIR, "security.json")
MIN_KEY_LENGTH = 12


def _hash_key(key: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", key.encode("utf-8"), salt, 310_000
    ).hex()


def admin_key_configured() -> bool:
    return _load_config() is not None


def verify_admin_key(key: str) -> bool:
    config = _load_config()
    if config is None or not key:
        return False
    try:
        salt = bytes.fromhex(config["salt"])
        expected = config["key_hash"]
    except (KeyError, TypeError, ValueError):
        return False
    return hmac.compare_digest(_hash_key(key, salt), expected)


def configure_admin_key(key: str) -> None:
    if len(key) < MIN_KEY_LENGTH:
        raise ValueError(
            f"The administrator key must contain at least {MIN_KEY_LENGTH} characters."
        )

    os.makedirs(CONFIG_DIR, exist_ok=True)
    salt = os.urandom(16)
    config = {
        "version": 1,
        "salt": salt.hex(),
        "key_hash": _hash_key(key, salt),
    }

    fd, temporary_path = tempfile.mkstemp(
        prefix="security_", suffix=".tmp", dir=CONFIG_DIR
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(config, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, CONFIG_FILE)
    finally:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)


def _load_config() -> Optional[dict]:
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as stream:
            data = json.load(stream)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError, TypeError):
        return None


def main() -> int:
    print("IPQ/LFR administrator key configuration")
    key = getpass.getpass("New administrator key: ")
    confirmation = getpass.getpass("Confirm administrator key: ")
    if key != confirmation:
        print("The keys do not match.")
        return 1
    try:
        configure_admin_key(key)
    except ValueError as exc:
        print(exc)
        return 1
    print(f"Administrator key configured in: {CONFIG_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
