import hashlib
import os
import subprocess
from io import StringIO
from pathlib import Path

import jinja2
from pyinfra import host
from pyinfra.facts.files import Sha256File
from pyinfra.facts.server import Command
from pyinfra.operations import files, server, systemd
from pyinfra.operations.util import any_changed
from release import artifact, fetch, frontend_bundle
from routes import BACKEND_PATHS, SSE_PATH
from server_setup import certificate, nginx_site, postgres_db
from server_setup.nginx_site import modern_http2
from server_setup.secrets import load, put_secret

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
UV = "/usr/local/bin/uv"
UV_ENV = {"UV_PYTHON_INSTALL_DIR": "/opt/uv/python"}
PYTHON = (REPO / ".python-version").read_text().strip()
# the backend and its vhost must agree on it
SNAPSHOTS_PREFIX = "/_snapshots"

d = host.data
name = d.name
unit = name.replace("_", "-")
opt = f"/opt/{name}"
backend_root = f"{opt}/backend"
bot_root = f"{opt}/bot"
www = f"/var/www/{name}"
env_dir = f"/etc/{name}"
lib_dir = f"/var/lib/{name}"
snapshot_dir = f"{lib_dir}/snapshots"
bot_state_dir = f"/var/lib/{name}-bot"
domain, api_domain, bot_domain = d.domain, f"api.{d.domain}", f"bot.{d.domain}"
site = f"https://{domain}"

build = fetch(os.environ.get("RELEASE_TAG", ""))
secrets = load(str(HERE / f"secrets/{d.stage}.sops.yaml"))


def secret_file(filename: str) -> str:
    # bytes, not text mode: universal newlines would rewrite a \r\n
    out = subprocess.run(
        [
            "sops",
            "decrypt",
            "--input-type",
            "binary",
            "--output-type",
            "binary",
            str(HERE / f"secrets/{d.stage}/{filename}.sops"),
        ],
        check=True,
        stdout=subprocess.PIPE,
    ).stdout
    return out.decode()


def render(template: str, **values) -> str:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(HERE / "templates"),
        trim_blocks=True,
        keep_trailing_newline=True,
        undefined=jinja2.StrictUndefined,
    )
    return env.get_template(template).render(**values)


def env_file(values: dict) -> str:
    for key, value in values.items():
        if "'" in str(value):
            raise ValueError(
                f"{key} holds a single quote, which the env file cannot carry"
            )
    return "".join(f"{key}='{value}'\n" for key, value in values.items())


def put(template: str, dest: str, **values):
    return files.put(
        name=f"Install {dest}",
        src=StringIO(render(template, **values)),
        dest=dest,
        mode="644",
    )


def digest(*paths: Path) -> str:
    sha = hashlib.sha256()
    for path in paths:
        sha.update(path.read_bytes())
    return sha.hexdigest()[:16]


def put_binary(name: str, src: Path, dest: str, **kwargs):
    # --diff reads a replaced binary as text and crashes; force takes put's create path, which skips it
    remote = host.get_fact(Sha256File, path=dest)
    local = hashlib.sha256(src.read_bytes()).hexdigest()
    force = remote is not None and remote != local
    return files.put(name=name, src=str(src), dest=dest, force=force, **kwargs)


def deployed(marker: str) -> str:
    return host.get_fact(Command, f"cat {marker} 2>/dev/null || true") or ""


def venv(
    root: str,
    wheels: list[Path],
    requirements: Path,
    reinstall: list[str],
    changes: list,
):
    # A marker, not the uploads' did_change: a run that uploaded then failed
    # must not look finished to the next one.
    expected = digest(*wheels, requirements)
    python = host.get_fact(
        Command,
        f"{root}/.venv/bin/python -c 'import sys; print(\"%d.%d\" % sys.version_info[:2])' 2>/dev/null || true",
    )
    if python == PYTHON and deployed(f"{root}/.venv/.deployed") == expected:
        return
    pip = f"{UV} pip install --no-cache --python {root}/.venv/bin/python"
    rebuild = [f"rm -rf {root}/.venv", f"{UV} venv --python {PYTHON} {root}/.venv"]
    changes.append(
        server.shell(
            name=f"Install {root}",
            commands=[
                *(rebuild if python != PYTHON else []),
                f"{pip} --requirement {root}/requirements.txt",
                f"{pip} {' '.join(f'--reinstall-package {p}' for p in reinstall)} "
                + " ".join(f"{root}/wheels/{w.name}" for w in wheels),
                f"find {root}/wheels -mindepth 1 -maxdepth 1 "
                + " ".join(f"! -name {w.name}" for w in wheels)
                + " -exec rm -rf {} +",
                f"echo {expected} > {root}/.venv/.deployed",
            ],
            _sudo_user=name,
            _env=UV_ENV,
            # uv reads uv.toml from the working directory: the SSH user's home is off limits
            _chdir=root,
        )
    )


def service(
    service_name: str, template: str, changes: list, port: int | None = None, **values
):
    units = [put(template, f"/etc/systemd/system/{service_name}.service", **values)]
    if port is not None:
        units.append(
            put(
                "listen.socket.j2",
                f"/etc/systemd/system/{service_name}.socket",
                service_name=service_name,
                port=port,
            )
        )
    systemd.daemon_reload(
        name=f"Reload units for {service_name}", _if=any_changed(*units)
    )
    handover = port is not None and (
        host.get_fact(Command, f"systemctl is-active {service_name}.socket || true")
        != "active"
    )
    if handover:
        # facts predate every op: a running=True after this stop would read "running" and skip
        server.shell(
            name=f"Hand {service_name}'s port to its socket",
            commands=[
                f"systemctl stop {service_name}.service",
                f"systemctl enable --now {service_name}.socket",
                f"systemctl start {service_name}.service",
            ],
        )
    elif port is not None:
        systemd.service(
            name=f"{service_name} socket",
            service=f"{service_name}.socket",
            running=True,
            enabled=True,
        )
    systemd.service(name=service_name, service=service_name, running=True, enabled=True)
    if not handover:
        systemd.service(
            name=f"Restart {service_name}",
            service=service_name,
            restarted=True,
            _if=any_changed(*units, *changes),
        )


# --- Runtime user and directories

server.group(name="App group", group=name, system=True)
server.user(
    name="App user",
    user=name,
    group=name,
    home=opt,
    shell="/usr/sbin/nologin",
    system=True,
    ensure_home=False,
    create_home=False,
)
files.directory(name="App root", path=opt, user=name, group=name, mode="755")
files.directory(name="Env dir", path=env_dir, user="root", group=name, mode="750")
files.directory(name="App lib dir", path=lib_dir, user=name, group=name, mode="751")
files.directory(
    name="Snapshot dir", path=snapshot_dir, user=name, group="www-data", mode="2750"
)
if host.get_fact(
    Command,
    f"find {snapshot_dir} \\( ! -group www-data -o ! -perm -g=r \\) -print -quit 2>/dev/null || true",
    _sudo=True,
):
    server.shell(
        name="Snapshots nginx can read",
        commands=[f"chgrp -R www-data {snapshot_dir}", f"chmod -R g+rX {snapshot_dir}"],
    )
# `uv venv`, run as the app user, would otherwise try to download the
# interpreter into a root-owned dir and fail EACCES
files.directory(
    name="uv Python dir",
    path=UV_ENV["UV_PYTHON_INSTALL_DIR"],
    user="root",
    group=name,
    mode="755",
)
if not any(
    line.startswith(f"cpython-{PYTHON}")
    for line in (
        host.get_fact(
            Command, f"ls {UV_ENV['UV_PYTHON_INSTALL_DIR']} 2>/dev/null || true"
        )
        or ""
    ).split()
):
    server.shell(
        name=f"Python {PYTHON}",
        commands=[f"{UV} python install --no-cache {PYTHON}"],
        _env=UV_ENV,
    )

postgres_db(database=name, owner=name)
postgres_units = (
    host.get_fact(
        Command,
        "systemctl list-units --plain --no-legend --state=active 'postgresql@*.service' | awk '{print $1}'",
    )
    or ""
).split()
if len(postgres_units) != 1:
    raise RuntimeError(
        f"expected one running PostgreSQL cluster, found {postgres_units}"
    )
postgres_unit = postgres_units[0]

# --- Certificates

certificate(domain)
if d.public_api:
    certificate(api_domain)

# --- Backend

files.directory(
    name="Backend root", path=backend_root, user=name, group=name, mode="755"
)
# operator tooling run by hand with the deployed venv, never imported by the service
files.sync(
    name="Backend ops scripts",
    src=str(REPO / "backend/scripts"),
    dest=f"{backend_root}/scripts",
    user=name,
    group=name,
    mode="755",
    exclude_dir="__pycache__",
)
backend_wheels = [
    artifact(build, "archon_engine-*.whl"),
    artifact(build, "archon-*.whl"),
]
backend_requirements = artifact(build, "backend-requirements.txt")
files.directory(
    name="Backend wheels",
    path=f"{backend_root}/wheels",
    user=name,
    group=name,
    mode="755",
)
backend = [
    put_binary(
        name=f"Upload {w.name}",
        src=w,
        dest=f"{backend_root}/wheels/{w.name}",
        user=name,
        group=name,
    )
    for w in backend_wheels
]
backend.append(
    files.put(
        name="Backend requirements",
        src=str(backend_requirements),
        dest=f"{backend_root}/requirements.txt",
        user=name,
        group=name,
    )
)
venv(
    backend_root,
    backend_wheels,
    backend_requirements,
    ["archon", "archon-engine"],
    backend,
)

# peer auth over the socket: the app runs as the OS user that owns its database
database_url = f"postgresql:///{name}?host=/var/run/postgresql"
backend_env = {
    "PYTHONOPTIMIZE": 1,
    "ENVIRONMENT": d.environment,
    "SITE_URL_BASE": site,
    "FRONTEND_URL": site,
    "API_BASE_URL": site,
    "DATABASE_URL": database_url,
    "MAIL_SERVER": "smtp.gmail.com",
    "MAIL_PORT": 587,
    "MAIL_USE_TLS": "true",
    "MAIL_USERNAME": "codex.of.the.damned@gmail.com",
    "MAIL_FROM": "codex.of.the.damned@gmail.com",
    "MAIL_FROM_NAME": d.app_name,
    "MAIL_PASSWORD": secrets["mail_password"],
    "JWT_PRIVATE_KEY": secrets["jwt_private_key"],
    "JWT_PUBLIC_KEYS": secrets["jwt_public_keys"],
    # the backend reads CLIENTID/SECRET, not CLIENT_ID/CLIENT_SECRET
    "DISCORD_CLIENTID": secrets["discord_client_id"],
    "DISCORD_SECRET": secrets["discord_client_secret"],
    "DISCORD_REDIRECT_URI": f"{site}/auth/discord/callback",
    "DISCORD_BOT_TOKEN": secrets["discord_bot_token"],
    "WEBAUTHN_RP_ID": domain,
    "WEBAUTHN_RP_NAME": d.app_name,
    "WEBAUTHN_ORIGIN": site,
    "VEKN_SYNC_ENABLED": "true",
    "VEKN_SYNC_INTERVAL_HOURS": 24,
    "TWDA_SYNC_ENABLED": "true",
    "VEKN_API_BASE_URL": "https://www.vekn.net/api",
    "VEKN_API_USERNAME": secrets["vekn_username"],
    "VEKN_API_PASSWORD": secrets["vekn_password"],
    "VEKN_PUSH": d.vekn_push,
    # Per-env keypair (beta and prod must NOT share). Rotating it invalidates
    # every existing browser subscription.
    "VAPID_PUBLIC_KEY": secrets["vapid_public_key"],
    "VAPID_PRIVATE_KEY": secrets["vapid_private_key"],
    "VAPID_SUBJECT": "mailto:lionel.panhaleux@gmail.com",
    "SNAPSHOT_DIR": snapshot_dir,
    "SNAPSHOT_ACCEL_PREFIX": SNAPSHOTS_PREFIX,
    "FEEDBACK_GITHUB_CLIENT_ID": secrets["feedback_github_client_id"],
    "FEEDBACK_GITHUB_INSTALLATION_ID": secrets["feedback_github_installation_id"],
    # a path: systemd's EnvironmentFile cannot carry a multi-line PEM
    "FEEDBACK_GITHUB_PRIVATE_KEY": f"{env_dir}/feedback_github_app.pem",
    "GITHUB_OAUTH_CLIENT_ID": secrets["github_oauth_client_id"],
    "GITHUB_OAUTH_SECRET": secrets["github_oauth_secret"],
    "GITHUB_OAUTH_REDIRECT_URI": f"{site}/auth/github/callback",
    "OFFICIALS_CONTACTS_FILE": f"{env_dir}/officials_contacts.json",
    **d.backend_env_extra,
}
# only production writes to the public archive: without these, every submission skips
if d.twda_push:
    backend_env |= {
        "TWDA_GITHUB_CLIENT_ID": secrets["twda_github_client_id"],
        "TWDA_GITHUB_INSTALLATION_ID": secrets["twda_github_installation_id"],
        "TWDA_GITHUB_FORK_INSTALLATION_ID": secrets["twda_github_fork_installation_id"],
        "TWDA_GITHUB_FORK_OWNER": "vtes-biased",
        "TWDA_GITHUB_PRIVATE_KEY": f"{env_dir}/twda_github_app.pem",
    }
backend.append(
    put_secret(
        f"{unit}-backend env",
        env_file(backend_env),
        f"{env_dir}/{unit}-backend.env",
        group=name,
        mode="640",
    )
)
secret_files = ["officials_contacts.json", "feedback_github_app.pem"]
if d.twda_push:
    secret_files.append("twda_github_app.pem")
else:
    files.file(name="No TWDA key", path=f"{env_dir}/twda_github_app.pem", present=False)
for filename in secret_files:
    backend.append(
        put_secret(
            filename,
            secret_file(filename),
            f"{env_dir}/{filename}",
            group=name,
            mode="640",
        )
    )
service(
    f"{unit}-backend",
    "backend.service.j2",
    backend,
    name=name,
    unit=unit,
    backend_root=backend_root,
    port=d.backend_port,
    env_dir=env_dir,
    lib_dir=lib_dir,
    postgres_unit=postgres_unit,
)

# --- Public read API: a second unit off the backend's venv

if d.public_api:
    public_api_env = {
        "PYTHONOPTIMIZE": 1,
        "SITE_URL_BASE": site,
        "PUBLIC_API_URL_BASE": f"https://{api_domain}",
        "DATABASE_URL": database_url,
        "ENVIRONMENT": d.environment,
        "JWT_PUBLIC_KEYS": secrets["jwt_public_keys"],
        "SNAPSHOT_DIR": snapshot_dir,
        **d.public_api_env_extra,
    }
    api_env = put_secret(
        f"{unit}-public-api env",
        env_file(public_api_env),
        f"{env_dir}/{unit}-public-api.env",
        group=name,
        mode="640",
    )
    service(
        f"{unit}-public-api",
        "public-api.service.j2",
        [api_env],
        name=name,
        unit=unit,
        backend_root=backend_root,
        port=d.api_port,
        env_dir=env_dir,
        postgres_unit=postgres_unit,
    )

# --- Discord bot

files.directory(name="Bot root", path=bot_root, user=name, group=name, mode="755")
files.directory(name="Bot state", path=bot_state_dir, user=name, group=name, mode="750")
bot_wheel = artifact(build, "archon_discord_bot-*.whl")
files.directory(
    name="Bot wheels",
    path=f"{bot_root}/wheels",
    user=name,
    group=name,
    mode="755",
)
bot_requirements = artifact(build, "bot-requirements.txt")
bot = [
    put_binary(
        name=f"Upload {bot_wheel.name}",
        src=bot_wheel,
        dest=f"{bot_root}/wheels/{bot_wheel.name}",
        user=name,
        group=name,
    ),
    files.put(
        name="Bot requirements",
        src=str(bot_requirements),
        dest=f"{bot_root}/requirements.txt",
        user=name,
        group=name,
    ),
]
venv(bot_root, [bot_wheel], bot_requirements, ["archon-discord-bot"], bot)
bot_env = {
    "PYTHONOPTIMIZE": 1,
    "ARCHON_URL": f"http://127.0.0.1:{d.backend_port}",
    "ARCHON_FRONTEND_URL": site,
    "DISCORD_BOT_TOKEN": secrets["discord_bot_token"],
    "OAUTH_CLIENT_ID": secrets["bot_oauth_client_id"],
    "OAUTH_CLIENT_SECRET": secrets["bot_oauth_client_secret"],
    "OAUTH_REDIRECT_URI": f"https://{bot_domain}/oauth/callback",
    "CALLBACK_HOST": "127.0.0.1",
    "CALLBACK_PORT": d.bot_port,
    "TOKEN_DB_PATH": f"{bot_state_dir}/tokens.db",
}
bot.append(
    put_secret(
        f"{unit}-bot env",
        env_file(bot_env),
        f"{env_dir}/{unit}-bot.env",
        group=name,
        mode="640",
    )
)
service(
    f"{unit}-bot",
    "bot.service.j2",
    bot,
    name=name,
    unit=unit,
    bot_root=bot_root,
    env_dir=env_dir,
    bot_state_dir=bot_state_dir,
)

# --- Frontend

files.directory(name="Frontend root", path=www, user=name, group=name, mode="755")
tarball = frontend_bundle(build)
bundle = digest(tarball)
put_binary(
    name="Frontend bundle",
    src=tarball,
    dest=f"{www}/frontend-dist.tar.gz",
    user=name,
    group=name,
)
if deployed(f"{www}/.bundle") != bundle:
    server.shell(
        name="Swap in the frontend",
        commands=[
            f"rm -rf {www}/dist.new",
            f"mkdir {www}/dist.new",
            f"tar -xzf {www}/frontend-dist.tar.gz -C {www}/dist.new",
            f"chown -R {name}:{name} {www}/dist.new",
            f"if [ -d {www}/dist ]; then rm -rf {www}/dist.prev && mv {www}/dist {www}/dist.prev; fi",
            f"mv {www}/dist.new {www}/dist",
            f"echo {bundle} > {www}/.bundle",
        ],
    )

# --- Vhosts

http2 = modern_http2(host.get_fact(Command, "nginx -v 2>&1"))
available = "/etc/nginx/sites-available"
vhosts = [
    put(
        "app.conf.j2",
        f"{available}/{name}_app.conf",
        domain=domain,
        modern_http2=http2,
        dist=f"{www}/dist",
        previous_dist=f"{www}/dist.prev",
        backend_paths=BACKEND_PATHS,
        sse_path=SSE_PATH,
        backend_port=d.backend_port,
        snapshot_accel_prefix=SNAPSHOTS_PREFIX,
        snapshot_dir=snapshot_dir,
    ),
    files.link(
        name=f"Enable {name}_app",
        path=f"/etc/nginx/sites-enabled/{name}_app.conf",
        target=f"{available}/{name}_app.conf",
    ),
]
if d.public_api:
    zone = f"{name}_public_api"
    vhosts += [
        put(
            "api-limits.conf.j2", f"/etc/nginx/conf.d/{name}_api_limits.conf", zone=zone
        ),
        put(
            "api.conf.j2",
            f"{available}/{name}_api.conf",
            domain=api_domain,
            modern_http2=http2,
            zone=zone,
            backend_port=d.backend_port,
            api_port=d.api_port,
        ),
        files.link(
            name=f"Enable {name}_api",
            path=f"/etc/nginx/sites-enabled/{name}_api.conf",
            target=f"{available}/{name}_api.conf",
        ),
    ]
server.shell(
    name="Validate nginx config", commands=["nginx -t"], _if=any_changed(*vhosts)
)
systemd.service(
    name="Reload nginx", service="nginx", reloaded=True, _if=any_changed(*vhosts)
)

nginx_site(
    site=f"{name}_bot",
    domain=bot_domain,
    type="proxy",
    upstream=f"http://127.0.0.1:{d.bot_port}",
    client_max_body_size="1m",
)
