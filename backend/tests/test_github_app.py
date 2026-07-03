"""load_private_key must fail loudly on a bad key-file path: silently returning
the path string used to surface as PyJWT's cryptic InvalidKeyError (a raw 500)."""

import pytest
from src.github_app import load_private_key


def test_missing_key_file_raises_with_path():
    with pytest.raises(FileNotFoundError, match="/etc/nowhere/app.pem"):
        load_private_key("/etc/nowhere/app.pem")
