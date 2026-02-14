"""Centralized JWT configuration."""

import os

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_DEFAULT_SECRET = "dev-secret-change-in-production"
