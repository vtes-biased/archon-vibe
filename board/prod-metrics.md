# Production metrics through Fluent Bit

Doc-impact: `wiki/dev.md` (Deployment — the metrics paragraph, plus footprint and
alerts once measured).

## Landed

The metrics inputs, the remote-write output, the `fluent-bit-units` loop and the
wiki paragraph. Endpoint `prometheus-prod-65-prod-eu-west-2.grafana.net`, user
`3605422` (read from the stack's `grafanacloud-prom` datasource). The config
passes `fluent-bit --dry-run`; the loop was run once on beta (cgroup v2, Debian)
and reads every unit, PostgreSQL's template instance included.

## Resume here (owner executes every prod command)

1. `just setup-prod` — shows the diff (config, script, `fluent-bit-units` unit),
   then asks.
2. Check on the box that both run and what Fluent Bit now holds:

   ```
   ssh archon.vekn.net 'systemctl is-active fluent-bit fluent-bit-units; systemctl show fluent-bit -p MemoryCurrent -p MemoryPeak; sudo cat /var/lib/fluent-bit/textfile/units.prom | head -20; sudo journalctl -u fluent-bit --since "-10min" --no-pager | tail -20'
   ```

3. Claude then verifies the series through the Grafana API (the owner's
   `GRAFANA_TOKEN_VTESBIASED`), confirms the systemd collector's label names on
   real series, and applies the alert rules: a failed or restart-looping archon
   unit, available memory under 10 %, a memory full-stall rate over 10 %, and
   the host silent for 10 minutes — to a Discord contact point whose webhook the
   owner supplies.
4. **Close the line**: the metrics paragraph in `wiki/dev.md` gains the measured
   footprint and the alert list; delete the line and this file.
