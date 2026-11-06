"""Password hashing with argon2."""

from argon2 import PasswordHasher

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Return a salted argon2 hash, safe to store."""
    return _hasher.hash(password)
