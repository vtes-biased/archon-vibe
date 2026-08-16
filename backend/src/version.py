"""Runtime version, sourced from package metadata that hatch-vcs stamps from the
git tag at build time; falls back to a sentinel outside an installed package."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _dist_version

try:
    __version__ = _dist_version("archon")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"
