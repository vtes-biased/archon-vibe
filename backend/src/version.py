"""Runtime version of the backend.

Sourced from the installed package metadata, which hatch-vcs stamps from the git
tag at build time (see [tool.hatch.version] in pyproject.toml). Falls back to a
sentinel when the package isn't installed (e.g. running straight from a source
checkout without an editable install).
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _dist_version

try:
    __version__ = _dist_version("archon")
except PackageNotFoundError:  # not installed as a distribution
    __version__ = "0.0.0+unknown"
