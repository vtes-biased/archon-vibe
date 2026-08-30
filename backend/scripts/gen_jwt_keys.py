"""Generate the Ed25519 keypair Archon signs its JWTs with.

Emits two single-line, env-var-friendly base64url values:
  JWT_PRIVATE_KEY  — raw 32-octet seed; the APP ONLY. SECRET, ansible-vault,
                     never commit.
  JWT_PUBLIC_KEYS  — raw 32-octet public point; every verifier, the public API
                     included. Not secret. Space-separated when a rotation leaves
                     the retiring key in the set.

One keypair per environment (beta/prod each get their own). Rotating INVALIDATES
every live session unless the retiring public key stays in JWT_PUBLIC_KEYS.

Usage:  uv run python backend/scripts/gen_jwt_keys.py
"""

import base64

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def main() -> None:
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    print("JWT_PRIVATE_KEY=" + b64url(key.private_bytes_raw()))
    print("JWT_PUBLIC_KEYS=" + b64url(public))


if __name__ == "__main__":
    main()
