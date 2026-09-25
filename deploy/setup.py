from io import StringIO
from pathlib import Path

import server_setup as s
from pyinfra import host, logger
from pyinfra.facts.files import File
from pyinfra.facts.server import LinuxDistribution
from pyinfra.operations import apt, files, systemd
from pyinfra.operations.util import any_changed
from server_setup.secrets import load, put_secret

# prod only: beta's box belongs to the server-setup fleet
HERE = Path(__file__).resolve().parent
secrets = load(str(HERE / f"secrets/{host.data.stage}.sops.yaml"))

s.packages(postgres_version="17")
# they depend on PGDG's newest major: an upgrade would install it beside 17
apt.packages(
    name="No unversioned postgresql",
    packages=["postgresql", "postgresql-client"],
    present=False,
)
s.services(journal_max_use="256M", journal_max_age="1month", fail2ban=False)
s.nginx()
s.ssh()
s.firewall()
s.swap()
s.postgres_config(
    settings={
        "shared_buffers": "96MB",
        "max_connections": "20",
        "effective_cache_size": "384MB",
    }
)
s.postgres_backups(
    access_key=secrets["remote_backup_access_key"],
    secret_key=secrets["remote_backup_secret_key"],
    restic_password=secrets["remote_backup_restic_password"],
    healthcheck_url=secrets["db_backup_healthcheck_url"],
    check_healthcheck_url=secrets["db_backup_check_healthcheck_url"],
    bucket="archon-db-backups",
)

# --- Logs: the journal to the VEKN Grafana Cloud stack, with Alloy's labels

key = files.download(
    name="Fluent Bit apt key",
    src="https://packages.fluentbit.io/fluentbit.key",
    dest="/etc/apt/keyrings/fluentbit.asc",
    mode="644",
)
codename = host.get_fact(LinuxDistribution)["release_meta"]["VERSION_CODENAME"]
repo = files.put(
    name="Fluent Bit apt repo",
    src=StringIO(
        "deb [signed-by=/etc/apt/keyrings/fluentbit.asc] "
        f"https://packages.fluentbit.io/ubuntu/{codename} {codename} main\n"
    ),
    dest="/etc/apt/sources.list.d/fluent-bit.list",
    mode="644",
)
apt.update(name="Refresh apt for Fluent Bit", _if=any_changed(key, repo))
apt.packages(name="Fluent Bit", packages=["fluent-bit"])
files.directory(name="Fluent Bit state", path="/var/lib/fluent-bit", mode="700")
fluent_bit = [
    files.template(
        name="Fluent Bit config",
        src=str(HERE / "templates/fluent-bit.conf.j2"),
        dest="/etc/fluent-bit/fluent-bit.conf",
        mode="644",
        loki_host="logs-prod-012.grafana.net",
        loki_user="1798381",
        host_name=host.name,
    ),
    files.put(
        name="Journal level mapping",
        src=str(HERE / "templates/journal.lua"),
        dest="/etc/fluent-bit/journal.lua",
        mode="644",
    ),
    put_secret(
        "Loki token",
        f"GC_LOKI_PASSWORD={secrets['grafana_cloud_loki_password']}\n",
        "/etc/fluent-bit/secrets.env",
    ),
]
unit_override = files.put(
    name="Fluent Bit token and memory cap",
    src=StringIO(
        "[Service]\nEnvironmentFile=/etc/fluent-bit/secrets.env\nMemoryMax=40M\n"
    ),
    dest="/etc/systemd/system/fluent-bit.service.d/override.conf",
    mode="644",
)
systemd.daemon_reload(name="Reload units for Fluent Bit", _if=unit_override.did_change)
systemd.service(name="fluent-bit", service="fluent-bit", running=True, enabled=True)
systemd.service(
    name="Restart fluent-bit",
    service="fluent-bit",
    restarted=True,
    _if=any_changed(unit_override, *fluent_bit),
)

if host.get_fact(File, path="/var/run/reboot-required"):
    logger.warning(f"{host.name}: REBOOT REQUIRED for a kernel or system update")
