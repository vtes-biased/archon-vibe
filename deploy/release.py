import json
import os
import subprocess
import urllib.request
from functools import cache
from pathlib import Path

REPO = "vtes-biased/archon-vibe"
BUILD = Path(__file__).parent / "build"


@cache
def fetch(tag: str = "") -> Path:
    """The release's assets in build/<tag>/, downloaded once. BUILD_DIR points at a
    local build instead. Plain urllib, no gh: a laptop and a CI runner behave alike."""
    if local := os.environ.get("BUILD_DIR"):
        return Path(local)
    headers = {"Accept": "application/vnd.github+json"}
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    api = f"https://api.github.com/repos/{REPO}/releases/" + (
        f"tags/{tag}" if tag else "latest"
    )
    release = json.load(
        urllib.request.urlopen(urllib.request.Request(api, headers=headers), timeout=30)
    )
    assets = {
        asset["name"]: asset["browser_download_url"] for asset in release["assets"]
    }
    if "frontend-dist.tar.gz" not in assets:
        raise RuntimeError(
            f"{release['tag_name']} has no frontend-dist.tar.gz: re-run the release-artifacts workflow"
        )
    out = BUILD / release["tag_name"]
    out.mkdir(parents=True, exist_ok=True)
    for name, url in assets.items():
        dest = out / name
        if not dest.exists():
            partial = dest.with_name(name + ".part")
            urllib.request.urlretrieve(url, partial)
            partial.rename(dest)
    print(f"Deploying {release['tag_name']} from {REPO}")
    return out


def artifact(build: Path, pattern: str) -> Path:
    # a local build dir keeps every version it built: the newest wins
    found = list(build.glob(pattern))
    if not found:
        raise RuntimeError(f"{build} has no {pattern}")
    return max(found, key=lambda path: path.stat().st_mtime)


def frontend_bundle(build: Path) -> Path:
    """A release ships frontend-dist.tar.gz; a local build leaves frontend-dist/, packed here."""
    dist = build / "frontend-dist"
    if not dist.is_dir():
        return artifact(build, "frontend-dist.tar.gz")
    tarball = build / "frontend-dist.tar.gz"
    # COPYFILE_DISABLE: macOS tar would add ._ AppleDouble files for extended attributes
    subprocess.run(
        ["tar", "-czf", str(tarball), "-C", str(dist), "."],
        check=True,
        env={**os.environ, "COPYFILE_DISABLE": "1"},
    )
    return tarball
