"""JWT signing and verification: the one place the token protocol lives.

The app holds the private half and is the only process that can mint; every
verifier — the public API included — holds public keys only.
"""

import base64
import functools
import hashlib
import os

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

JWT_ALGORITHM = "EdDSA"

AUDIENCE_APP = "archon"
AUDIENCE_API = "archon-api"

# Derived, not configured: an unset key therefore *works*, in development where
# both processes derive the same pair. assert_production_keys is the only thing
# separating that from production.
_DEV_SEED = b"archon-development-signing-seed."


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64url(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _kid(public: Ed25519PublicKey) -> str:
    raw = public.public_bytes(Encoding.Raw, PublicFormat.Raw)
    return _b64url(hashlib.sha256(raw).digest())[:16]


def _dev_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(_DEV_SEED)


def _configured_private() -> Ed25519PrivateKey | None:
    value = os.getenv("JWT_PRIVATE_KEY", "")
    return Ed25519PrivateKey.from_private_bytes(_unb64url(value)) if value else None


@functools.cache
def _signing_key() -> tuple[Ed25519PrivateKey, str]:
    key = _configured_private() or _dev_key()
    return key, _kid(key.public_key())


@functools.cache
def _verification_keys() -> dict[str, Ed25519PublicKey]:
    """kid -> public key."""
    keys: dict[str, Ed25519PublicKey] = {}
    private = _configured_private()
    if private:
        keys[_kid(private.public_key())] = private.public_key()
    for value in os.getenv("JWT_PUBLIC_KEYS", "").replace(",", " ").split():
        public = Ed25519PublicKey.from_public_bytes(_unb64url(value))
        keys[_kid(public)] = public
    if not keys:
        public = _dev_key().public_key()
        keys[_kid(public)] = public
    return keys


def assert_production_keys(*, signing: bool) -> None:
    """Both lifespans call this. `signing` is the app, the only process that may
    hold the private half."""
    if os.getenv("ENVIRONMENT", "development") == "development":
        return
    if _kid(_dev_key().public_key()) in _verification_keys():
        raise RuntimeError(
            "Refusing to boot on the development signing key. Generate a keypair "
            "with `just jwt-keys`, then set JWT_PRIVATE_KEY (the app) and "
            "JWT_PUBLIC_KEYS (every verifier)."
        )
    if signing and not _configured_private():
        raise RuntimeError("The app mints tokens: set JWT_PRIVATE_KEY.")
    if not signing and _configured_private():
        raise RuntimeError(
            "This process only verifies tokens: it must not hold JWT_PRIVATE_KEY."
        )


def sign(payload: dict, audience: str | list[str]) -> str:
    key, kid = _signing_key()
    return jwt.encode(
        payload | {"aud": audience},
        key,
        algorithm=JWT_ALGORITHM,
        headers={"kid": kid},
    )


def decode(token: str, audience: str, *, verify_exp: bool = True) -> dict:
    """Raises jwt.InvalidTokenError — ExpiredSignatureError, a wrong audience and an
    unknown `kid` alike, which every caller already answers 401 on."""
    key = _verification_keys().get(jwt.get_unverified_header(token).get("kid"))
    if key is None:
        raise jwt.InvalidTokenError("Unknown key id")
    return jwt.decode(
        token,
        key,
        algorithms=[JWT_ALGORITHM],
        audience=audience,
        options={"verify_exp": verify_exp},
    )
