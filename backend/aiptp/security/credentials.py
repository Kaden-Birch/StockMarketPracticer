"""Encrypted-at-rest provider API keys (PRD §27). Fernet symmetric
encryption; the key file lives in the data directory with owner-only
permissions (OS keychain integration arrives with the desktop shell)."""

import os
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from ..storage.models import ProviderCredential

KEY_FILENAME = "secret.key"


def _fernet(data_dir: Path) -> Fernet:
    key_path = data_dir / KEY_FILENAME
    if not key_path.exists():
        key = Fernet.generate_key()
        key_path.write_bytes(key)
        os.chmod(key_path, 0o600)
    return Fernet(key_path.read_bytes())


def store_key(session: Session, data_dir: Path, provider: str, value: str) -> None:
    encrypted = _fernet(data_dir).encrypt(value.encode()).decode()
    existing = session.get(ProviderCredential, provider)
    if existing:
        existing.encrypted_value = encrypted
        existing.updated_at = datetime.now(timezone.utc)
    else:
        session.add(ProviderCredential(provider=provider, encrypted_value=encrypted))


def load_key(session: Session, data_dir: Path, provider: str) -> str | None:
    row = session.get(ProviderCredential, provider)
    if row is None:
        return None
    try:
        return _fernet(data_dir).decrypt(row.encrypted_value.encode()).decode()
    except InvalidToken:
        return None


def delete_key(session: Session, provider: str) -> bool:
    row = session.get(ProviderCredential, provider)
    if row is None:
        return False
    session.delete(row)
    return True
