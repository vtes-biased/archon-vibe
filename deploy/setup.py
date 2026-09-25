from pathlib import Path

import server_setup as s
from pyinfra import host, logger
from pyinfra.facts.files import File
from pyinfra.operations import files
from server_setup.secrets import load

# prod only: beta's box belongs to the server-setup fleet
secrets = load(
    str(Path(__file__).resolve().parent / f"secrets/{host.data.stage}.sops.yaml")
)

s.packages(postgres_version="17")
files.file(
    name="Retire the Ansible journal cap",
    path="/etc/systemd/journald.conf.d/50-cap.conf",
    present=False,
)
s.services(journal_max_use="256M", fail2ban=False)
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

if host.get_fact(File, path="/var/run/reboot-required"):
    logger.warning(f"{host.name}: REBOOT REQUIRED for a kernel or system update")
