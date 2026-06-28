"""Transparent encryption-at-rest for sensitive subscription config values.

Secret-looking config keys (API keys, cookies, tokens, ...) are encrypted before
being written to the database and decrypted when read back. The rest of the app
keeps working with plaintext config dicts, so this is invisible to callers.

The key is taken from the DASHBOARD_SECRET_KEY env var when set; otherwise a key
file is generated once under the data directory (chmod 600). If the cryptography
library is unavailable we fall back to storing plaintext and log a warning, so an
existing deployment never breaks.
"""

import base64
import hashlib
import logging
from functools import lru_cache
from typing import Any, Dict, Optional

from daily_briefing.config import SECRET_HINTS

from app.config import get_settings


logger = logging.getLogger(__name__)

_ENC_PREFIX = "enc:v1:"

try:  # pragma: no cover - exercised indirectly
    from cryptography.fernet import Fernet, InvalidToken

    _CRYPTO_AVAILABLE = True
except Exception:  # pragma: no cover - fallback path
    Fernet = None  # type: ignore[assignment]
    InvalidToken = Exception  # type: ignore[assignment]
    _CRYPTO_AVAILABLE = False


def _is_secret_key(key: str) -> bool:
    upper = key.upper()
    return any(hint in upper for hint in SECRET_HINTS)


def _coerce_fernet_key(raw: str) -> bytes:
    candidate = raw.encode("utf-8")
    try:
        Fernet(candidate)
        return candidate
    except Exception:
        digest = hashlib.sha256(candidate).digest()
        return base64.urlsafe_b64encode(digest)


def _load_or_create_key() -> bytes:
    settings = get_settings()
    if settings.secret_key:
        return _coerce_fernet_key(settings.secret_key)
    key_file = settings.secret_key_file
    key_file.parent.mkdir(parents=True, exist_ok=True)
    if key_file.exists():
        return key_file.read_bytes().strip()
    key = Fernet.generate_key()
    key_file.write_bytes(key)
    key_file.chmod(0o600)
    return key


@lru_cache(maxsize=1)
def _fernet() -> Optional["Fernet"]:
    if not _CRYPTO_AVAILABLE:
        logger.warning(
            "cryptography is not installed; subscription secrets will be stored in plaintext. "
            "Install 'cryptography' to enable encryption at rest."
        )
        return None
    try:
        return Fernet(_load_or_create_key())
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("failed to initialise encryption key, storing secrets in plaintext: %s", exc)
        return None


def encrypt_config(config: Dict[str, Any]) -> Dict[str, str]:
    cipher = _fernet()
    result: Dict[str, str] = {}
    for key, value in (config or {}).items():
        text = "" if value is None else str(value)
        if cipher and text and _is_secret_key(key) and not text.startswith(_ENC_PREFIX):
            token = cipher.encrypt(text.encode("utf-8")).decode("ascii")
            result[key] = f"{_ENC_PREFIX}{token}"
        else:
            result[key] = text
    return result


def decrypt_config(config: Dict[str, Any]) -> Dict[str, str]:
    cipher = _fernet()
    result: Dict[str, str] = {}
    for key, value in (config or {}).items():
        text = "" if value is None else str(value)
        if text.startswith(_ENC_PREFIX):
            token = text[len(_ENC_PREFIX):]
            if cipher:
                try:
                    result[key] = cipher.decrypt(token.encode("ascii")).decode("utf-8")
                    continue
                except InvalidToken:
                    logger.warning("could not decrypt config key %s; leaving encrypted value as-is", key)
            result[key] = text
        else:
            result[key] = text
    return result
