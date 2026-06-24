"""Generate a VAPID keypair for Web Push (#314).

Emits two single-line, env-var-friendly base64url values:
  VAPID_PRIVATE_KEY  — raw 32-octet private scalar (loaded by push_service via
                       Vapid01.from_raw); SECRET, store in ansible-vault, never commit.
  VAPID_PUBLIC_KEY   — raw 65-octet uncompressed public point; this IS the browser's
                       applicationServerKey, served per-env by GET /api/push/vapid-key.

One keypair per environment (beta/prod each get their own). Rotating the keypair
INVALIDATES every existing browser subscription — they must re-subscribe.

Usage:  uv run python backend/scripts/gen_vapid_keys.py
"""

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def main() -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    private_raw = key.private_numbers().private_value.to_bytes(32, "big")
    public_raw = key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    print("VAPID_PRIVATE_KEY=" + b64url(private_raw))
    print("VAPID_PUBLIC_KEY=" + b64url(public_raw))
    print("VAPID_SUBJECT=mailto:admin@example.com  # set to a real contact mailto:/https URL")


if __name__ == "__main__":
    main()
